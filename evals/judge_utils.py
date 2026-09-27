"""
judge_utils.py — Shared helpers for LLM-as-a-Judge evaluation scripts.

Every agent judge eval (job, freelance, certification, proposal) imports from here
so that:
  1. The judge LLM is always built the same way (gpt-4o, temperature=0).
  2. LangSmith experiment logging follows a single, consistent pattern.
  3. Score-table printing is uniform across all scripts.

LangSmith is configured via environment variables already set in .env:
    LANGSMITH_API_KEY      — your LangSmith API key
    LANGSMITH_PROJECT      — project name (career-compass)
    LANGSMITH_TRACING=true — enables automatic LangChain tracing
"""

from __future__ import annotations

import sys
# Force UTF-8 output so box-drawing characters (─, │, ┌, etc.) print correctly
# on Windows terminals that default to cp1252 encoding.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
from datetime import datetime, timezone
from typing import Any

from langchain_openai import ChatOpenAI


# ─────────────────────────────────────────────────────────────────────────────
# Judge LLM
# ─────────────────────────────────────────────────────────────────────────────

def build_judge_llm() -> ChatOpenAI:
    """
    Create a deterministic GPT-4o judge LLM.

    WHY GPT-4o and not the same model as the generators?
    Using a *different* (and stronger) model avoids the self-serving-bias
    problem where the same model that generated the answer gives it
    artificially high scores.  GPT-4o is also highly consistent at
    structured scoring tasks with temperature=0.
    """
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0,      # Deterministic — same prompt → same scores
        api_key=os.getenv("OPENAI_API_KEY"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LangSmith logging
# ─────────────────────────────────────────────────────────────────────────────

def log_to_langsmith(
    results: list[dict[str, Any]],
    dataset_name: str,
    experiment_prefix: str,
) -> str | None:
    """
    Push evaluation results to LangSmith as a named experiment.

    HOW IT WORKS (langsmith 0.3.x API)
    ────────────────────────────────────
    1. Load .env so the LANGSMITH_API_KEY is available (needed when running
       scripts directly from the terminal — not all shells inherit .env vars).
    2. Create (or reuse) a Dataset with the given name.
    3. Upsert Examples into the dataset using client.create_examples().
    4. For every scored result, create a traced Run and attach per-criterion
       Feedback items (one per scoring criterion, score normalised 0–1).

    Parameters
    ──────────
    results         list of dicts, one per test case.  Must contain:
                      "case_id"     (str)  — unique identifier
                      "question"    (str)  — the input query
                      "answer"      (str)  — the agent's output
                      "scores"      (dict) — {criterion: float, 1-5 scale}
                      "reasoning"   (dict) — {criterion: str explanation}
    dataset_name    Name shown in the LangSmith Datasets tab.
    experiment_prefix  Short label; timestamp is appended automatically.

    Returns the experiment name string, or None if LangSmith is unavailable.
    """
    try:
        # ── 0. Load .env so the API key is available when running scripts ─────
        # LangSmith's Client reads LANGSMITH_API_KEY from the environment.
        # When scripts are run directly, the .env may not be loaded yet.
        from dotenv import load_dotenv
        load_dotenv()

        from langsmith import Client

        client = Client()

        # ── 1. Create or retrieve the dataset ────────────────────────────────
        # list_datasets() returns an iterator; we materialise it to check.
        datasets = list(client.list_datasets(dataset_name=dataset_name))
        if datasets:
            dataset = datasets[0]
        else:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description=f"LLM-as-a-Judge eval cases for {dataset_name}",
            )

        # ── 2. Upsert examples into the dataset ───────────────────────────────
        # client.create_examples() is the correct v0.3 API for bulk insertion.
        # It is idempotent by default when no duplicate checking is enforced,
        # so re-running the eval just adds new example versions.
        client.create_examples(
            dataset_id=dataset.id,
            inputs=[{"question": r["question"]} for r in results],
            outputs=[{"reference": r.get("ground_truth", "")} for r in results],
        )

        # ── 3. Build a timestamped experiment name ────────────────────────────
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        experiment_name = f"{experiment_prefix}-{ts}"

        # ── 4. Log each scored result as a Run with per-criterion Feedback ────
        # IMPORTANT: In langsmith v0.3, create_run() returns None.
        # You must generate your own UUID and pass it as run_id= so that
        # update_run() and create_feedback() can reference the same run.
        import uuid as _uuid
        project_name = os.getenv("LANGSMITH_PROJECT", "career-compass")

        for r in results:
            scores    = r.get("scores", {})
            reasoning = r.get("reasoning", {})

            # Generate a stable run ID for this eval case
            run_id = _uuid.uuid4()

            # Create the run entry (shows as a node in the LangSmith trace view)
            client.create_run(
                run_id=run_id,          # ← must be passed explicitly; not returned
                name=experiment_name,
                run_type="chain",
                inputs={"question": r["question"]},
                outputs={"answer": r["answer"]},
                project_name=project_name,
                tags=[experiment_prefix, r["case_id"]],
            )

            # Close the run immediately — synthetic eval runs don't have a duration
            client.update_run(run_id, end_time=datetime.now(timezone.utc))

            # Attach one feedback per criterion (score normalised from 1-5 → 0-1)
            for criterion, score in scores.items():
                client.create_feedback(
                    run_id=run_id,
                    key=criterion,
                    score=score / 5.0,
                    comment=reasoning.get(criterion, ""),
                    source_info={
                        "evaluator": "gpt-4o",
                        "experiment": experiment_name,
                    },
                )


        print(f"\nLogged to LangSmith experiment: {experiment_name}")
        print(f"  Project : {project_name}")
        print(f"  Dataset : {dataset_name}")
        print(f"  Runs    : {len(results)}")
        return experiment_name

    except ImportError:
        # langsmith is optional — the eval still saves CSV without it
        print("WARNING: langsmith not installed — skipping LangSmith logging.")
        return None
    except Exception as exc:
        # Never let LangSmith failures crash the eval run — just warn
        print(f"WARNING: LangSmith logging failed: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print helpers
# ─────────────────────────────────────────────────────────────────────────────

def print_scores_table(results: list[dict[str, Any]]) -> None:
    """
    Print a neat terminal table of per-case scores.

    Example output:
    ┌────────────────────────────┬────────────┬────────────┬──────────────┬─────────┐
    │ case_id                    │ relevance  │ groundedness │ skill_align │ overall │
    ├────────────────────────────┼────────────┼────────────┼──────────────┼─────────┤
    │ data_scientist_good_match  │    4.0     │    5.0     │    4.0       │  4.33   │
    └────────────────────────────┴────────────┴────────────┴──────────────┴─────────┘
    """
    if not results:
        print("No results to display.")
        return

    # Collect all criterion names from the first result
    criteria = list(results[0].get("scores", {}).keys())

    # Build rows
    rows = []
    for r in results:
        scores = r.get("scores", {})
        overall = r.get("overall_score", 0.0)
        row = [r["case_id"]] + [f"{scores.get(c, 0):.1f}" for c in criteria] + [f"{overall:.2f}"]
        rows.append(row)

    headers = ["case_id"] + criteria + ["overall"]

    # Calculate column widths
    col_widths = [max(len(h), max(len(row[i]) for row in rows)) for i, h in enumerate(headers)]

    # Print table
    def fmt_row(cells: list[str]) -> str:
        return "│ " + " │ ".join(c.ljust(w) for c, w in zip(cells, col_widths)) + " │"

    separator = "├─" + "─┼─".join("─" * w for w in col_widths) + "─┤"
    top       = "┌─" + "─┬─".join("─" * w for w in col_widths) + "─┐"
    bottom    = "└─" + "─┴─".join("─" * w for w in col_widths) + "─┘"

    print(top)
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))
    print(bottom)


def compute_overall(scores: dict[str, float]) -> float:
    """Return the simple average of all criterion scores (1–5 scale)."""
    if not scores:
        return 0.0
    return round(sum(scores.values()) / len(scores), 2)
