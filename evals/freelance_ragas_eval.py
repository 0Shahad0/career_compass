"""
freelance_ragas_eval.py — RAGAS edge-case evaluation for the CareerCompass Freelance Agent.

Keeps retrieval deterministic by replacing the three live tools with static
fixture values from freelance_edge_cases.json, then evaluates the generated
answer against those same contexts using RAGAS metrics.

FIXES applied vs. the original version
──────────────────────────────────────
1. user_profile in fixture JSON is now the correct UserProfile Pydantic shape
   (personal_information / skills as [{"name":...}] / experience as [{"title":...}]).
   The old flat dict format caused AttributeError at runtime inside the agent.

2. Results are now also pushed to LangSmith as a named experiment so runs are
   visible in the LangSmith dashboard alongside the judge evals.
   (LangchainLLMWrapper was already present in the original — kept as-is.)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "freelance_edge_cases.json"

sys.path.insert(0, str(ROOT))

import pandas as pd
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_correctness, answer_relevancy, faithfulness

import backend.agents.freelance_agent as freelance_module
from backend.schemas.profile import UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Static tool fixture
# ─────────────────────────────────────────────────────────────────────────────

class StaticTool:
    """
    Simple drop-in replacement for a LangChain StructuredTool.
    Returns a fixed value regardless of what payload is passed.
    """

    def __init__(self, value: Any):
        self.value = value

    def invoke(self, payload: dict) -> Any:
        return self.value


# ─────────────────────────────────────────────────────────────────────────────
# Context builder for RAGAS
# ─────────────────────────────────────────────────────────────────────────────

def _as_context(case: dict) -> str:
    """
    Combine the three fixture data sources into one JSON context string.
    RAGAS uses this as the 'context' field for faithfulness scoring.
    """
    evidence = {
        "historical_market_analysis": case["market_analysis"],
        "live_freelancer_api_results": case["live_projects"],
        "live_web_search_results": case["web_opportunities"],
    }
    return json.dumps(evidence, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Run one case against the real Freelance Agent
# ─────────────────────────────────────────────────────────────────────────────

def _run_agent_with_case(case: dict) -> str:
    """
    Patch the three Freelance Agent tools with static fixtures, run the agent,
    then restore the originals using try/finally.

    The fixture user_profile dict is converted to a UserProfile Pydantic object
    before passing to the agent — this mirrors the real API path.
    """
    # Convert fixture profile dict → UserProfile Pydantic object
    raw_profile = case["state"].get("user_profile", {})
    profile_obj = UserProfile.model_validate(raw_profile)

    state = dict(case["state"])
    state["user_profile"] = profile_obj

    # Save originals
    original_market = freelance_module.analyze_historical_market
    original_api    = freelance_module.search_freelancer_api
    original_web    = freelance_module.search_freelance_projects

    try:
        # Patch with fixtures
        freelance_module.analyze_historical_market = lambda skills: case["market_analysis"]
        freelance_module.search_freelancer_api     = StaticTool(case["live_projects"])
        freelance_module.search_freelance_projects = StaticTool(case["web_opportunities"])

        result = freelance_module.freelance_agent(state)

        # The freelance agent returns structured projects, not a text analysis.
        # Serialise the projects list to a JSON string so RAGAS can score it.
        projects = result.get("freelance_projects", [])
        return json.dumps(
            [p.model_dump() if hasattr(p, "model_dump") else p for p in projects],
            ensure_ascii=False,
            indent=2,
        )

    finally:
        # Always restore originals
        freelance_module.analyze_historical_market = original_market
        freelance_module.search_freelancer_api     = original_api
        freelance_module.search_freelance_projects = original_web


# ─────────────────────────────────────────────────────────────────────────────
# Case loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_cases(path: Path, case_id: str | None) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]
        if not cases:
            raise ValueError(f"No freelance eval case found for id: {case_id}")
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail checks
# ─────────────────────────────────────────────────────────────────────────────

def _guardrail_checks(case: dict, answer: str) -> list[str]:
    """
    Simple must-include / must-not-include checks from the fixture.
    Run in addition to RAGAS metrics.
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
# RAGAS dataset builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_dataset(cases: list[dict], answers: list[str]) -> Dataset:
    return Dataset.from_dict({
        "question":   [case["state"].get("query", "") for case in cases],
        "answer":     answers,
        "contexts":   [[_as_context(case)] for case in cases],
        "reference":  [case["reference"] for case in cases],
    })


# ─────────────────────────────────────────────────────────────────────────────
# LangSmith push
# ─────────────────────────────────────────────────────────────────────────────

def _push_to_langsmith(
    cases: list[dict],
    answers: list[str],
    df: "pd.DataFrame",
    experiment_name: str,
) -> None:
    """Push RAGAS scores to LangSmith as a named experiment.

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
        project = os.getenv("LANGSMITH_PROJECT", "career-compass")

        for case, answer, (_, row) in zip(cases, answers, df.iterrows()):
            run_id = client.create_run(
                name=experiment_name,
                run_type="chain",
                inputs={"question": case["state"].get("query", "")},
                outputs={"answer": answer},
                project_name=project,
                tags=["ragas", "freelance-agent"],
            )
            # Close the run immediately — synthetic eval runs don't have a duration
            client.update_run(run_id, end_time=datetime.now(timezone.utc))

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

def main() -> None:
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(
        description="Run RAGAS edge-case evals for the freelancer agent."
    )
    parser.add_argument("--case-id", help="Run one case from the JSON fixture.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=CASES_PATH,
        help="Path to the freelance edge-case JSON fixture.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evals" / "freelance_ragas_results.csv",
        help="Where to write the per-case RAGAS scores.",
    )
    args = parser.parse_args()

    # ── Step 1: Load & run cases ──────────────────────────────────────────────
    cases   = _load_cases(args.cases, args.case_id)
    answers = [_run_agent_with_case(case) for case in cases]

    # ── Step 2: Build RAGAS dataset ───────────────────────────────────────────
    dataset = _build_dataset(cases, answers)

    # ── Step 3: Configure evaluators ─────────────────────────────────────────
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(model="gpt-4o-mini", temperature=0)
    )
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small")
    )

    # ── Step 4: RAGAS evaluation ──────────────────────────────────────────────
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, answer_correctness],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        raise_exceptions=False,
    )

    # ── Step 5: Build results DataFrame ──────────────────────────────────────
    df = result.to_pandas()
    df.insert(0, "case_id",     [c["id"]                      for c in cases])
    df.insert(1, "description", [c.get("description", "")     for c in cases])
    df["guardrail_failures"] = [
        "; ".join(_guardrail_checks(case, answer))
        for case, answer in zip(cases, answers, strict=True)
    ]

    # ── Step 6: Save CSV ──────────────────────────────────────────────────────
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    # ── Step 7: Push to LangSmith ─────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    _push_to_langsmith(cases, answers, df, experiment_name=f"freelance-ragas-{ts}")

    # ── Step 8: Print summary ─────────────────────────────────────────────────
    print(df[[
        "case_id",
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
        "guardrail_failures",
    ]].to_string(index=False))
    print(f"\nSaved detailed results to: {args.out}")


if __name__ == "__main__":
    main()
