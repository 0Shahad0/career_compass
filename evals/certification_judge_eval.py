"""
certification_judge_eval.py — LLM-as-a-Judge evaluation for the Certification Agent.

HOW IT WORKS
─────────────
1. Load test cases from certification_eval_cases.json.
2. For each case, run the real Certification Agent (recommend_certifications).
3. Send (query, profile context, agent output) to a GPT-4o judge LLM.
4. The judge returns structured JSON scores on 4 criteria (each 1–5).
5. Log every run + scores to LangSmith as a named experiment.
6. Print a scores table and save certification_judge_results.csv.

NOTE: The certification agent uses semantic search over a local dataset
(no external API calls for the recommendation step), so no tool patching is
needed — we can call the real agent directly with the fixture profile.

SCORING CRITERIA (1 = poor, 5 = excellent)
──────────────────────────────────────────
  relevance          — Certifications match the user's field and career goals?
  specificity        — Recommendations name real certs (e.g., SAA-C03)?
  missing_skills_accuracy — Gap skills truly missing from the profile?
  roadmap_quality    — Logical learning path / ordering?
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
CASES_PATH = ROOT / "evals" / "certification_eval_cases.json"

sys.path.insert(0, str(ROOT))

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.agents.certification_agent2 import recommend_certifications
from backend.schemas.profile import UserProfile
from evals.judge_utils import build_judge_llm, compute_overall, log_to_langsmith, print_scores_table


# ─────────────────────────────────────────────────────────────────────────────
# Structured judge output schema
# ─────────────────────────────────────────────────────────────────────────────

class CertJudgeScore(BaseModel):
    relevance: int               = Field(ge=1, le=5, description="Certs match user field/goals?")
    specificity: int             = Field(ge=1, le=5, description="Names real, specific certs?")
    missing_skills_accuracy: int = Field(ge=1, le=5, description="Gap skills truly missing?")
    roadmap_quality: int         = Field(ge=1, le=5, description="Logical learning path?")

    relevance_reason:               str
    specificity_reason:             str
    missing_skills_accuracy_reason: str
    roadmap_quality_reason:         str


# ─────────────────────────────────────────────────────────────────────────────
# Run one case through the real Certification Agent
# ─────────────────────────────────────────────────────────────────────────────

def _run_case(case: dict) -> tuple[str, str]:
    """
    Convert the fixture profile to a UserProfile object, call recommend_certifications,
    and return (serialised_recommendations, profile_context_text).
    """
    raw_profile = case["state"].get("user_profile", {})
    profile_obj = UserProfile.model_validate(raw_profile)

    skills   = [s.name for s in profile_obj.skills]
    exp      = [e.title for e in profile_obj.experience]
    summary  = profile_obj.professional_summary or "none"
    profile_context = (
        f"Summary: {summary}\n"
        f"Skills: {', '.join(skills) or 'none'}\n"
        f"Experience: {', '.join(exp) or 'none'}"
    )

    state = {
        "user_id":    "eval-test",
        "query":      case["state"].get("query", ""),
        "user_profile": profile_obj,
        "offset": 0,
        "limit":  10,
    }

    result = recommend_certifications(state)

    # Serialise certifications list to JSON string for the judge prompt
    certs  = result.get("certifications", [])
    answer = json.dumps(
        [c.model_dump() if hasattr(c, "model_dump") else c for c in certs],
        ensure_ascii=False,
        indent=2,
    )
    return answer, profile_context


# ─────────────────────────────────────────────────────────────────────────────
# Judge scoring
# ─────────────────────────────────────────────────────────────────────────────

judge_llm = build_judge_llm().with_structured_output(CertJudgeScore)

JUDGE_SYSTEM = """\
You are an expert evaluator for a career guidance AI called CareerCompass.
Your task is to score the Certification Agent's recommendations on four criteria, each 1–5.

Scoring rubric:
  5 = Excellent   — fully satisfies the criterion with no notable flaws
  4 = Good        — mostly satisfies with minor issues
  3 = Acceptable  — partially satisfies; noticeable room for improvement
  2 = Poor        — significant shortcomings
  1 = Unacceptable — completely fails the criterion

Penalise invented certification names heavily. Penalise recommending CISSP or CISM to
a complete beginner who clearly needs entry-level certs.
"""


def _judge_response(
    query: str,
    profile_context: str,
    answer: str,
    reference: str,
) -> CertJudgeScore:
    """Score the certification agent's output."""
    user_prompt = f"""
QUERY
─────
{query}

USER PROFILE
────────────
{profile_context}

REFERENCE ANSWER (what a good response should include)
───────────────────────────────────────────────────────
{reference}

CERTIFICATION AGENT RESPONSE (serialised recommendations)
──────────────────────────────────────────────────────────
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
            reference=case.get("reference", ""),
        )

        scores = {
            "relevance":               score_obj.relevance,
            "specificity":             score_obj.specificity,
            "missing_skills_accuracy": score_obj.missing_skills_accuracy,
            "roadmap_quality":         score_obj.roadmap_quality,
        }
        reasoning = {
            "relevance":               score_obj.relevance_reason,
            "specificity":             score_obj.specificity_reason,
            "missing_skills_accuracy": score_obj.missing_skills_accuracy_reason,
            "roadmap_quality":         score_obj.roadmap_quality_reason,
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
    print("CERTIFICATION AGENT — LLM-as-a-Judge Results")
    print("─" * 60)
    print_scores_table(all_results)

    rows = []
    for r in all_results:
        row = {"case_id": r["case_id"], "overall_score": r["overall_score"]}
        row.update(r["scores"])
        for k, v in r["reasoning"].items():
            row[f"{k}_reason"] = v
        rows.append(row)

    out = ROOT / "evals" / "certification_judge_results.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nSaved to: {out}")

    log_to_langsmith(
        results=all_results,
        dataset_name="certification-agent-evals",
        experiment_prefix="cert-judge",
    )
