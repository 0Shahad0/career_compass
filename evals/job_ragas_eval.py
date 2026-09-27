"""
job_ragas_eval.py — RAGAS edge-case evaluation for the CareerCompass Job Agent.

Keeps retrieval deterministic by replacing the three live tools with static
fixture values from job_edge_cases.json, then evaluates the generated answer
against those same contexts using RAGAS metrics.

FIXES applied vs. the original version
──────────────────────────────────────
1. user_profile in fixture JSON is now the correct UserProfile Pydantic shape
   (personal_information / skills as [{"name":...}] / experience as [{"title":...}]).
   The old flat dict format caused AttributeError at runtime.

2. The RAGAS evaluator LLM is now wrapped in LangchainLLMWrapper (required by
   RAGAS ≥ 0.3 — passing a raw ChatOpenAI previously raised a TypeError).

3. Results are now also pushed to LangSmith as a named experiment so runs are
   visible in the LangSmith dashboard alongside the judge evals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "job_edge_cases.json"

sys.path.insert(0, str(ROOT))

import pandas as pd
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# RAGAS wrappers — required since RAGAS 0.3+
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_correctness, answer_relevancy, faithfulness

import backend.agents.job_agent as job_agent_module
from backend.agents.job_agent import job_agent
from backend.schemas.profile import UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Static tool fixture — replaces live tools during eval
# ─────────────────────────────────────────────────────────────────────────────

class StaticTool:
    """
    Simple drop-in replacement for a LangChain StructuredTool.
    Returns a fixed value regardless of what payload is passed.
    This keeps eval results deterministic — no network calls, no API costs.
    """

    def __init__(self, result):
        self.result = result

    def invoke(self, args=None):
        return self.result


# ─────────────────────────────────────────────────────────────────────────────
# Case loading
# ─────────────────────────────────────────────────────────────────────────────

def load_cases(path: Path = CASES_PATH) -> list[dict]:
    """Load eval cases from the JSON fixture file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Run a single case against the real Job Agent
# ─────────────────────────────────────────────────────────────────────────────

def run_case(case: dict) -> dict:
    """
    Patch the three Job Agent tools with static fixtures, run the agent,
    then restore the originals.  Using try/finally guarantees cleanup even
    if the agent raises an exception.
    """
    print(f"\nRunning: {case['id']}")

    # Convert the fixture user_profile dict to a UserProfile Pydantic object.
    # This mirrors what load_agent_profile() does in the real API path.
    raw_profile = case["state"].get("user_profile", {})
    profile_obj = UserProfile.model_validate(raw_profile)

    # Inject the Pydantic object so the agent receives the right type
    state = dict(case["state"])
    state["user_profile"] = profile_obj

    # Save originals before patching
    original_search  = job_agent_module.search_jobs
    original_onet    = job_agent_module.get_occupation_information
    original_resume  = job_agent_module.get_required_skills

    try:
        # Patch with deterministic fixtures
        job_agent_module.search_jobs               = StaticTool(case.get("job_results", []))
        job_agent_module.get_occupation_information = StaticTool(case.get("onet_result", {}))
        job_agent_module.get_required_skills        = StaticTool(case.get("resume_result", {}))

        result = job_agent(state)

        return {
            "case_id":      case["id"],
            "description":  case.get("description", ""),
            "question":     state["query"],
            "answer":       result.get("job_analysis", ""),
            "ground_truth": case.get("reference", ""),
            "job_results":  case.get("job_results", []),
            "onet_result":  case.get("onet_result", {}),
            "resume_result": case.get("resume_result", {}),
        }

    finally:
        # Always restore originals
        job_agent_module.search_jobs               = original_search
        job_agent_module.get_occupation_information = original_onet
        job_agent_module.get_required_skills        = original_resume


# ─────────────────────────────────────────────────────────────────────────────
# Build the RAGAS dataset
# ─────────────────────────────────────────────────────────────────────────────

def build_ragas_dataset(results: list[dict]) -> Dataset:
    """
    RAGAS expects a dataset with four columns:
      question  — the user's input query
      answer    — the agent's generated response
      contexts  — list of context strings the answer should be grounded in
      reference — the gold-standard reference answer
    """
    rows = []
    for result in results:
        contexts = []

        # Each tool's output is a separate context string
        if result.get("job_results"):
            contexts.append(
                "Job Search Results:\n"
                + json.dumps(result["job_results"], ensure_ascii=False, default=str)
            )
        if result.get("onet_result"):
            contexts.append(
                "O*NET Information:\n"
                + json.dumps(result["onet_result"], ensure_ascii=False, default=str)
            )
        if result.get("resume_result"):
            contexts.append(
                "Resume Dataset Information:\n"
                + json.dumps(result["resume_result"], ensure_ascii=False, default=str)
            )

        rows.append({
            "question":  result["question"],
            "answer":    result["answer"],
            "contexts":  contexts,
            "reference": result["ground_truth"],
        })

    return Dataset.from_list(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail checks (keyword-based, run after eval)
# ─────────────────────────────────────────────────────────────────────────────

def _guardrail_checks(case: dict, answer: str) -> list[str]:
    """
    Simple must-include / must-not-include checks from the fixture.
    These run in addition to RAGAS metrics.
    """
    failures = []
    lower = answer.lower()

    for text in case.get("must_include", []):
        if text.lower() not in lower:
            failures.append(f"missing required text: {text!r}")

    for text in case.get("must_not_include", []):
        if text.lower() in lower:
            failures.append(f"contains forbidden text: {text!r}")

    return failures


# ─────────────────────────────────────────────────────────────────────────────
# LangSmith experiment push (optional — gracefully skipped if unavailable)
# ─────────────────────────────────────────────────────────────────────────────

def _push_to_langsmith(df: pd.DataFrame, experiment_name: str) -> None:
    """
    Push the RAGAS scores to LangSmith as feedback on a named experiment.
    Failures are caught and printed so they never block the eval run.

    Uses the langsmith 0.3.x API:
      - load_dotenv() first so LANGSMITH_API_KEY is in the environment
      - client.create_run() to create a synthetic traced run per case
      - client.update_run() to close it immediately (end_time required)
      - client.create_feedback() to attach each RAGAS metric score
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()   # Ensure LANGSMITH_API_KEY is available from .env

        from datetime import datetime, timezone
        from langsmith import Client

        client = Client()
        import uuid as _uuid
        project = os.getenv("LANGSMITH_PROJECT", "career-compass")

        for _, row in df.iterrows():
            # Generate our own UUID — create_run() returns None in langsmith v0.3
            run_id = _uuid.uuid4()

            # Create a traced run entry in LangSmith for this eval case
            client.create_run(
                run_id=run_id,
                name=experiment_name,
                run_type="chain",
                inputs={"question": row.get("question", "")},
                outputs={"answer": row.get("answer", "")},
                project_name=project,
                tags=["ragas", "job-agent"],
            )
            # Close the run immediately — synthetic eval runs don't have a duration
            client.update_run(run_id, end_time=datetime.now(timezone.utc))

            # Attach each RAGAS metric score as a feedback item (already 0-1)
            for metric in ["faithfulness", "answer_relevancy", "answer_correctness"]:
                score = row.get(metric)
                if score is not None and not pd.isna(score):
                    client.create_feedback(
                        run_id=run_id,
                        key=f"ragas_{metric}",
                        score=float(score),
                        source_info={"evaluator": "ragas", "experiment": experiment_name},
                    )

        print(f"\nPushed RAGAS results to LangSmith experiment: {experiment_name}")
        print(f"  Project: {project}")

    except ImportError:
        print("WARNING: langsmith not installed -- skipping LangSmith push.")
    except Exception as exc:
        print(f"WARNING: LangSmith push failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import datetime, timezone

    cases = load_cases()

    # ── Step 1: Run all cases through the Job Agent ───────────────────────────
    results = [run_case(case) for case in cases]
    print("\nAll cases completed.")

    # ── Step 2: Build RAGAS dataset ───────────────────────────────────────────
    dataset = build_ragas_dataset(results)

    # ── Step 3: Configure evaluator models ───────────────────────────────────
    # WHY LangchainLLMWrapper?  RAGAS 0.3+ requires its own wrapper types;
    # passing a raw ChatOpenAI raises a TypeError at evaluate() time.
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(model="gpt-4o-mini", temperature=0)
    )
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small")
    )

    # ── Step 4: Run RAGAS evaluation ──────────────────────────────────────────
    print("\nRunning RAGAS evaluation …")
    evaluation_result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, answer_correctness],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        raise_exceptions=False,   # Keep going even if one metric fails
    )

    # ── Step 5: Build results DataFrame ──────────────────────────────────────
    df = evaluation_result.to_pandas()
    df.insert(0, "case_id",     [r["case_id"]     for r in results])
    df.insert(1, "description", [r["description"] for r in results])
    df["guardrail_failures"] = [
        "; ".join(_guardrail_checks(case, r["answer"]))
        for case, r in zip(cases, results)
    ]

    # ── Step 6: Save CSV ──────────────────────────────────────────────────────
    output_file = ROOT / "evals" / "job_ragas_results.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)

    # ── Step 7: Push to LangSmith ─────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    _push_to_langsmith(df, experiment_name=f"job-ragas-{ts}")

    # ── Step 8: Print summary ─────────────────────────────────────────────────
    print("\nRAGAS evaluation complete.")
    print(f"Results saved to: {output_file}\n")
    print(df[[
        "case_id",
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
        "guardrail_failures",
    ]].to_string(index=False))