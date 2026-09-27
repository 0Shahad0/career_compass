"""
freelance_judge_eval.py — LLM-as-a-Judge evaluation for the CareerCompass Freelance Agent.

HOW IT WORKS
─────────────
1. Load test cases from freelance_edge_cases.json (same fixture as the RAGAS eval).
2. For each case, run the real Freelance Agent with static tool fixtures.
3. Send (query, profile context, agent output) to a GPT-4o judge LLM.
4. The judge returns structured JSON scores on 4 criteria (each 1–5).
5. Log every run + scores to LangSmith as a named experiment.
6. Print a scores table and save freelance_judge_results.csv.

SCORING CRITERIA (1 = poor, 5 = excellent)
──────────────────────────────────────────
  relevance       — Projects match the user's skills and query?
  groundedness    — No invented URLs, titles, or budgets?
  skill_alignment — Matching/missing skills correctly identified?
  actionability   — Clear next steps for the user?
"""

from __future__ import annotations

import sys
# Force UTF-8 output on Windows (default terminal encoding is cp1252 which
# cannot encode box-drawing characters used in the score table).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "freelance_edge_cases.json"

sys.path.insert(0, str(ROOT))

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import backend.agents.freelance_agent as freelance_module
from backend.agents.freelance_agent import freelance_agent
from backend.schemas.profile import UserProfile
from evals.judge_utils import build_judge_llm, compute_overall, log_to_langsmith, print_scores_table


# ─────────────────────────────────────────────────────────────────────────────
# Structured judge output schema
# ─────────────────────────────────────────────────────────────────────────────

class FreelanceJudgeScore(BaseModel):
    relevance: int       = Field(ge=1, le=5, description="Projects match user skills/query?")
    groundedness: int    = Field(ge=1, le=5, description="No invented URLs/titles/budgets?")
    skill_alignment: int = Field(ge=1, le=5, description="Matching/missing skills correct?")
    actionability: int   = Field(ge=1, le=5, description="Clear next steps for the user?")

    relevance_reason:       str
    groundedness_reason:    str
    skill_alignment_reason: str
    actionability_reason:   str


# ─────────────────────────────────────────────────────────────────────────────
# Static tool fixture
# ─────────────────────────────────────────────────────────────────────────────

class StaticTool:
    def __init__(self, value: Any):
        self.value = value

    def invoke(self, payload: dict) -> Any:
        return self.value


# ─────────────────────────────────────────────────────────────────────────────
# Run one case through the real Freelance Agent
# ─────────────────────────────────────────────────────────────────────────────

def _run_case(case: dict) -> tuple[str, str]:
    """
    Patch tools, run the agent, restore tools.
    Returns (serialised_projects_json, profile_context_text).
    """
    raw_profile = case["state"].get("user_profile", {})
    profile_obj = UserProfile.model_validate(raw_profile)

    state = dict(case["state"])
    state["user_profile"] = profile_obj

    skills   = [s.name for s in profile_obj.skills]
    exp      = [e.title for e in profile_obj.experience]
    location = profile_obj.personal_information.location or "unspecified"
    profile_context = (
        f"Skills: {', '.join(skills) or 'none'}\n"
        f"Experience: {', '.join(exp) or 'none'}\n"
        f"Location: {location}"
    )

    orig_market = freelance_module.analyze_historical_market
    orig_api    = freelance_module.search_freelancer_api
    orig_web    = freelance_module.search_freelance_projects

    try:
        freelance_module.analyze_historical_market = lambda skills: case["market_analysis"]
        freelance_module.search_freelancer_api     = StaticTool(case["live_projects"])
        freelance_module.search_freelance_projects = StaticTool(case["web_opportunities"])

        result   = freelance_agent(state)
        projects = result.get("freelance_projects", [])

        # Serialise structured project objects to JSON string for the judge prompt
        answer = json.dumps(
            [p.model_dump() if hasattr(p, "model_dump") else p for p in projects],
            ensure_ascii=False,
            indent=2,
        )
        return answer, profile_context

    finally:
        freelance_module.analyze_historical_market = orig_market
        freelance_module.search_freelancer_api     = orig_api
        freelance_module.search_freelance_projects = orig_web


# ─────────────────────────────────────────────────────────────────────────────
# Judge scoring
# ─────────────────────────────────────────────────────────────────────────────

judge_llm = build_judge_llm().with_structured_output(FreelanceJudgeScore)

JUDGE_SYSTEM = """\
You are an expert evaluator for a career guidance AI called CareerCompass.
Your task is to score the Freelance Agent's response on four criteria, each 1–5.

Scoring rubric:
  5 = Excellent   — fully satisfies the criterion with no notable flaws
  4 = Good        — mostly satisfies with minor issues
  3 = Acceptable  — partially satisfies; noticeable room for improvement
  2 = Poor        — significant shortcomings
  1 = Unacceptable — completely fails the criterion

Penalise hallucinations (invented URLs, budgets, titles) very heavily (score 1).
Penalise cases where the agent recommends historical dataset jobs as live opportunities.
"""


def _judge_response(
    query: str,
    profile_context: str,
    answer: str,
    live_projects: Any,
) -> FreelanceJudgeScore:
    """Score the freelance agent's output using the GPT-4o judge."""
    user_prompt = f"""
QUERY
─────
{query}

USER PROFILE
────────────
{profile_context}

AVAILABLE LIVE PROJECTS (fixture — ground truth for groundedness scoring)
─────────────────────────────────────────────────────────────────────────
{json.dumps(live_projects, ensure_ascii=False, default=str, indent=2)}

FREELANCE AGENT RESPONSE (serialised project recommendations)
─────────────────────────────────────────────────────────────
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

        answer, profile_context = _run_case(case)

        score_obj = _judge_response(
            query=case["state"].get("query", ""),
            profile_context=profile_context,
            answer=answer,
            live_projects=case.get("live_projects", []),
        )

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
            "case_id":       case["id"],
            "question":      case["state"].get("query", ""),
            "answer":        answer,
            "ground_truth":  case.get("reference", ""),
            "scores":        scores,
            "reasoning":     reasoning,
            "overall_score": compute_overall(scores),
        }
        all_results.append(result)
        print(f"  overall: {result['overall_score']:.2f} / 5.00")

    print("\n" + "─" * 60)
    print("FREELANCE AGENT — LLM-as-a-Judge Results")
    print("─" * 60)
    print_scores_table(all_results)

    rows = []
    for r in all_results:
        row = {"case_id": r["case_id"], "overall_score": r["overall_score"]}
        row.update(r["scores"])
        for k, v in r["reasoning"].items():
            row[f"{k}_reason"] = v
        rows.append(row)

    out = ROOT / "evals" / "freelance_judge_results.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nSaved to: {out}")

    log_to_langsmith(
        results=all_results,
        dataset_name="freelance-agent-evals",
        experiment_prefix="freelance-judge",
    )
