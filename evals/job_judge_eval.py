"""
job_judge_eval.py — LLM-as-a-Judge evaluation for the CareerCompass Job Agent.

HOW IT WORKS
─────────────
1. Load test cases from job_edge_cases.json (same fixture as the RAGAS eval).
2. For each case, run the real Job Agent with static tool fixtures.
3. Send (query, profile context, agent output) to a GPT-4o judge LLM.
4. The judge returns structured JSON scores on 4 criteria (each 1–5).
5. Log every run + scores to LangSmith as a named experiment.
6. Print a scores table and save job_judge_results.csv.

WHY COMPLEMENT RAGAS?
──────────────────────
RAGAS measures faithfulness / relevancy / correctness via automated pipeline.
The LLM Judge adds richer, criteria-specific scores that RAGAS cannot capture
(e.g., "did the agent correctly identify skill gaps?" or "is the response
actionable?"). Together they give comprehensive coverage.

SCORING CRITERIA (1 = poor, 5 = excellent)
──────────────────────────────────────────
  relevance       — Does the answer address the user's job search query?
  groundedness    — Are job titles/URLs grounded in fixture data (no hallucinations)?
  skill_alignment — Are recommended jobs matched to the profile's actual skills?
  actionability   — Does the response give the user something concrete to do next?
"""

from __future__ import annotations

import sys
# Force UTF-8 output on Windows (default terminal encoding is cp1252 which
# cannot encode box-drawing characters used in the score table).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "job_edge_cases.json"

sys.path.insert(0, str(ROOT))

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import backend.agents.job_agent as job_agent_module
from backend.agents.job_agent import job_agent
from backend.schemas.profile import UserProfile

# Shared judge utilities (LangSmith logger, score-table printer, etc.)
from evals.judge_utils import build_judge_llm, compute_overall, log_to_langsmith, print_scores_table


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic model for structured judge output
# Using structured output prevents the judge from drifting into free-form text.
# ─────────────────────────────────────────────────────────────────────────────

class JobJudgeScore(BaseModel):
    """Structured scores returned by the GPT-4o judge for one job agent response."""

    relevance: int = Field(ge=1, le=5, description="Does the answer address the query?")
    groundedness: int = Field(ge=1, le=5, description="No hallucinated jobs/URLs?")
    skill_alignment: int = Field(ge=1, le=5, description="Jobs match the profile skills?")
    actionability: int = Field(ge=1, le=5, description="User knows what to do next?")

    relevance_reason:       str
    groundedness_reason:    str
    skill_alignment_reason: str
    actionability_reason:   str


# ─────────────────────────────────────────────────────────────────────────────
# Static tool fixture (deterministic tool replacements)
# ─────────────────────────────────────────────────────────────────────────────

class StaticTool:
    def __init__(self, result):
        self.result = result

    def invoke(self, args=None):
        return self.result


# ─────────────────────────────────────────────────────────────────────────────
# Run one case through the real Job Agent
# ─────────────────────────────────────────────────────────────────────────────

def _run_case(case: dict) -> tuple[str, str]:
    """
    Patch tools, run the agent, restore tools.
    Returns (job_analysis_text, profile_context_text).
    """
    # Convert fixture dict to proper UserProfile Pydantic object
    raw_profile = case["state"].get("user_profile", {})
    profile_obj = UserProfile.model_validate(raw_profile)

    state = dict(case["state"])
    state["user_profile"] = profile_obj

    # Extract a readable profile summary for the judge prompt
    skills   = [s.name for s in profile_obj.skills]
    exp      = [e.title for e in profile_obj.experience]
    location = (profile_obj.personal_information.location or "unspecified")
    profile_context = (
        f"Skills: {', '.join(skills) or 'none'}\n"
        f"Experience: {', '.join(exp) or 'none'}\n"
        f"Location: {location}"
    )

    # Save and patch tools
    orig_search = job_agent_module.search_jobs
    orig_onet   = job_agent_module.get_occupation_information
    orig_resume = job_agent_module.get_required_skills

    try:
        job_agent_module.search_jobs               = StaticTool(case.get("job_results", []))
        job_agent_module.get_occupation_information = StaticTool(case.get("onet_result", {}))
        job_agent_module.get_required_skills        = StaticTool(case.get("resume_result", {}))

        result = job_agent(state)
        return result.get("job_analysis", ""), profile_context

    finally:
        job_agent_module.search_jobs               = orig_search
        job_agent_module.get_occupation_information = orig_onet
        job_agent_module.get_required_skills        = orig_resume


# ─────────────────────────────────────────────────────────────────────────────
# Judge scoring
# ─────────────────────────────────────────────────────────────────────────────

# Build the judge LLM once at module level for efficiency
judge_llm = build_judge_llm().with_structured_output(JobJudgeScore)

# System prompt for the judge — stays fixed across all cases
JUDGE_SYSTEM = """\
You are an expert evaluator for a career guidance AI system called CareerCompass.
Your task is to score the Job Agent's response on four criteria, each from 1 to 5.

Scoring rubric:
  5 = Excellent   — fully satisfies the criterion with no notable flaws
  4 = Good        — mostly satisfies with minor issues
  3 = Acceptable  — partially satisfies; noticeable room for improvement
  2 = Poor        — significant shortcomings
  1 = Unacceptable — completely fails the criterion

Be a strict but fair evaluator. Penalise hallucinated content heavily.
"""


def _judge_response(
    query: str,
    profile_context: str,
    answer: str,
    available_jobs: list,
) -> JobJudgeScore:
    """
    Send the job agent's output to GPT-4o for structured scoring.

    We include the fixture job data so the judge can verify groundedness
    (i.e., check whether the agent invented jobs not present in the data).
    """
    user_prompt = f"""
QUERY
─────
{query}

USER PROFILE
────────────
{profile_context}

AVAILABLE JOBS (fixture — ground truth for groundedness scoring)
────────────────────────────────────────────────────────────────
{json.dumps(available_jobs, ensure_ascii=False, default=str, indent=2)}

JOB AGENT RESPONSE
──────────────────
{answer}

Score the response now.
"""
    return judge_llm.invoke([
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=user_prompt),
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    all_results = []

    for case in cases:
        print(f"\nEvaluating: {case['id']}")

        # 1. Run the agent
        answer, profile_context = _run_case(case)

        # 2. Score with the judge
        score_obj = _judge_response(
            query=case["state"].get("query", ""),
            profile_context=profile_context,
            answer=answer,
            available_jobs=case.get("job_results", []),
        )

        # 3. Pack into a uniform result dict (format expected by judge_utils)
        scores = {
            "relevance":       score_obj.relevance,
            "groundedness":    score_obj.groundedness,
            "skill_alignment": score_obj.skill_alignment,
            "actionability":   score_obj.actionability,
        }
        reasoning = {
            "relevance":       score_obj.relevance_reason,
            "groundedness":    score_obj.groundedness_reason,
            "skill_alignment": score_obj.skill_alignment_reason,
            "actionability":   score_obj.actionability_reason,
        }
        result = {
            "case_id":      case["id"],
            "question":     case["state"].get("query", ""),
            "answer":       answer,
            "ground_truth": case.get("reference", ""),
            "scores":       scores,
            "reasoning":    reasoning,
            "overall_score": compute_overall(scores),
        }
        all_results.append(result)
        print(f"  overall: {result['overall_score']:.2f} / 5.00")

    # ── Print summary table ───────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("JOB AGENT — LLM-as-a-Judge Results")
    print("─" * 60)
    print_scores_table(all_results)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    rows = []
    for r in all_results:
        row = {"case_id": r["case_id"], "overall_score": r["overall_score"]}
        row.update(r["scores"])
        for k, v in r["reasoning"].items():
            row[f"{k}_reason"] = v
        rows.append(row)

    out = ROOT / "evals" / "job_judge_results.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nSaved to: {out}")

    # ── Push to LangSmith ─────────────────────────────────────────────────────
    log_to_langsmith(
        results=all_results,
        dataset_name="job-agent-evals",
        experiment_prefix="job-judge",
    )
