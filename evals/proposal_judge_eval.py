"""
proposal_judge_eval.py — LLM-as-a-Judge evaluation for the CareerCompass Proposal Agent.

HOW IT WORKS
─────────────
1. Load test cases from proposal_eval_cases.json.
2. For each case, call generate_proposal() with the fixture profile and project details.
3. Send (project details, profile context, proposal text) to a GPT-4o judge.
4. The judge returns structured JSON scores on 5 criteria (each 1–5).
5. Log every run + scores to LangSmith as a named experiment.
6. Print a scores table and save proposal_judge_results.csv.

WHY A DIFFERENT MODEL AS JUDGE?
─────────────────────────────────
The proposal generator uses gpt-4.1-mini at temperature=0.4.
The judge uses gpt-4o at temperature=0. Using a different (stronger) model
avoids self-serving bias — the same model that generated the text tends to
rate its own outputs too favourably.

SCORING CRITERIA (1 = poor, 5 = excellent)
──────────────────────────────────────────
  relevance        — Proposal addresses the specific project?
  personalization  — Uses real profile facts, not generic filler?
  structure        — Hook → Proof → Close format?
  professionalism  — No filler phrases, no email headers, warm tone?
  actionability    — Clear, low-pressure call to action?
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
CASES_PATH = ROOT / "evals" / "proposal_eval_cases.json"

sys.path.insert(0, str(ROOT))

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.agents.proposal_agent import generate_proposal
from backend.schemas.profile import UserProfile
from evals.judge_utils import build_judge_llm, compute_overall, log_to_langsmith, print_scores_table


# ─────────────────────────────────────────────────────────────────────────────
# Structured judge output schema
# ─────────────────────────────────────────────────────────────────────────────

class ProposalJudgeScore(BaseModel):
    relevance: int        = Field(ge=1, le=5, description="Proposal addresses the specific project?")
    personalization: int  = Field(ge=1, le=5, description="Uses real profile facts?")
    structure: int        = Field(ge=1, le=5, description="Hook → Proof → Close format?")
    professionalism: int  = Field(ge=1, le=5, description="No filler phrases, good tone?")
    actionability: int    = Field(ge=1, le=5, description="Clear CTA at the end?")

    relevance_reason:       str
    personalization_reason: str
    structure_reason:       str
    professionalism_reason: str
    actionability_reason:   str


# ─────────────────────────────────────────────────────────────────────────────
# Run one case through the real Proposal Agent
# ─────────────────────────────────────────────────────────────────────────────

def _run_case(case: dict) -> tuple[str, str]:
    """
    Convert the fixture profile dict to a UserProfile object, call generate_proposal(),
    and return (proposal_text, profile_context_text).
    """
    profile_obj = UserProfile.model_validate(case["profile"])

    skills   = [s.name for s in profile_obj.skills]
    projects = [p.name for p in profile_obj.projects]
    exp      = [e.title for e in profile_obj.experience]
    summary  = profile_obj.professional_summary or "none"

    profile_context = (
        f"Summary: {summary}\n"
        f"Skills: {', '.join(skills) or 'none'}\n"
        f"Experience: {', '.join(exp) or 'none'}\n"
        f"Projects: {', '.join(projects) or 'none'}"
    )

    proposal = generate_proposal(
        profile=profile_obj,
        project_title=case["project_title"],
        project_description=case["project_description"],
        budget_or_rate=case.get("budget_or_rate"),
        matching_skills=case.get("matching_skills", []),
        missing_skills=case.get("missing_skills", []),
    )

    return proposal, profile_context


# ─────────────────────────────────────────────────────────────────────────────
# Judge scoring
# ─────────────────────────────────────────────────────────────────────────────

judge_llm = build_judge_llm().with_structured_output(ProposalJudgeScore)

JUDGE_SYSTEM = """\
You are an expert evaluator for a freelance proposal writing AI called CareerCompass.
Your task is to score a generated freelance proposal on five criteria, each 1–5.

Scoring rubric:
  5 = Excellent   — fully satisfies the criterion with no notable flaws
  4 = Good        — mostly satisfies with minor issues
  3 = Acceptable  — partially satisfies; noticeable room for improvement
  2 = Poor        — significant shortcomings
  1 = Unacceptable — completely fails the criterion

Specific penalisation rules:
  - If the proposal uses filler phrases like "I am writing to express my interest"
    or "I am the perfect candidate", penalise professionalism heavily (1-2).
  - If the proposal invents skills, projects, or experience not present in the
    user profile, penalise personalization heavily (1).
  - If the proposal lacks a call to action at the end, score actionability 1.
  - If the proposal has a subject line or email header, penalise professionalism.
"""


def _judge_proposal(
    project_title: str,
    project_description: str,
    profile_context: str,
    proposal_text: str,
    reference: str,
) -> ProposalJudgeScore:
    """Score the proposal using the GPT-4o judge."""
    user_prompt = f"""
PROJECT DETAILS
───────────────
Title: {project_title}
Description: {project_description}

USER PROFILE
────────────
{profile_context}

REFERENCE (what a good proposal should include)
───────────────────────────────────────────────
{reference}

GENERATED PROPOSAL
──────────────────
{proposal_text}

Score the proposal now.
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

        # 1. Run the proposal agent
        proposal, profile_context = _run_case(case)
        print(f"  Generated {len(proposal.split())} words")

        # 2. Score with the judge
        score_obj = _judge_proposal(
            project_title=case["project_title"],
            project_description=case["project_description"],
            profile_context=profile_context,
            proposal_text=proposal,
            reference=case.get("reference", ""),
        )

        scores = {
            "relevance":       score_obj.relevance,
            "personalization": score_obj.personalization,
            "structure":       score_obj.structure,
            "professionalism": score_obj.professionalism,
            "actionability":   score_obj.actionability,
        }
        reasoning = {
            "relevance":       score_obj.relevance_reason,
            "personalization": score_obj.personalization_reason,
            "structure":       score_obj.structure_reason,
            "professionalism": score_obj.professionalism_reason,
            "actionability":   score_obj.actionability_reason,
        }
        result = {
            "case_id":       case["id"],
            "question":      f"Write proposal for: {case['project_title']}",
            "answer":        proposal,
            "ground_truth":  case.get("reference", ""),
            "scores":        scores,
            "reasoning":     reasoning,
            "overall_score": compute_overall(scores),
        }
        all_results.append(result)
        print(f"  overall: {result['overall_score']:.2f} / 5.00")

    print("\n" + "─" * 60)
    print("PROPOSAL AGENT — LLM-as-a-Judge Results")
    print("─" * 60)
    print_scores_table(all_results)

    # Save CSV
    rows = []
    for r in all_results:
        row = {"case_id": r["case_id"], "overall_score": r["overall_score"]}
        row.update(r["scores"])
        for k, v in r["reasoning"].items():
            row[f"{k}_reason"] = v
        rows.append(row)

    out = ROOT / "evals" / "proposal_judge_results.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nSaved to: {out}")

    # Push to LangSmith
    log_to_langsmith(
        results=all_results,
        dataset_name="proposal-agent-evals",
        experiment_prefix="proposal-judge",
    )
