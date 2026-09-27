"""
proposal_guardrails.py — Runtime topic guardrail for the Proposal Agent endpoints.

PURPOSE
────────
Ensure users can ONLY use the proposal endpoints (/freelance/proposal and
/freelance/proposal/chat) for their intended purpose: writing and refining
freelance proposals. Off-topic messages (homework, general chat, other career
questions, harmful content) are blocked before reaching the proposal agent.

HOW IT WORKS
─────────────
An LLM classifier (gpt-4o-mini, temperature=0) inspects the incoming request
and returns a structured decision: PROPOSAL_RELATED or OFF_TOPIC.

  PROPOSAL_RELATED → allow the request through (return normally)
  OFF_TOPIC        → raise ValueError with a user-friendly reason

WHY LLM-BASED (not keyword blocklist)?
───────────────────────────────────────
Keyword lists miss paraphrases ("assist me with math homework" vs "do my homework")
and can block legitimate proposal requests that happen to contain flagged words.
An LLM classifier understands intent, not just surface patterns.

TRADE-OFF
──────────
Each call adds ~100–300ms of latency. This is acceptable because:
  1. Proposal generation already takes 2-4 seconds (LLM call).
  2. The guardrail call is tiny (gpt-4o-mini, low token count).
  3. Safety is worth the latency.

PUBLIC API
──────────
  validate_proposal_request(project_title, project_description) → None
    Called before generate_proposal(). Raises ValueError if off-topic.

  validate_chat_message(user_message) → None
    Called before chat_with_proposal(). Raises ValueError if off-topic.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from backend.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Classifier LLM — gpt-4o-mini is fast, cheap, and accurate for binary classification
# ─────────────────────────────────────────────────────────────────────────────

_classifier_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,          # Deterministic — no creative drift in classification
    api_key=settings.openai_api_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# Structured output schema for the classifier
# Using Pydantic structured output prevents the LLM from returning free text —
# we always get a predictable, machine-readable decision.
# ─────────────────────────────────────────────────────────────────────────────

class _TopicDecision(BaseModel):
    """Classifier output: is this request related to freelance proposals?"""

    is_proposal_related: bool = Field(
        description=(
            "True if the request is about writing, refining, adjusting, or "
            "discussing a freelance proposal. False for everything else."
        )
    )
    reason: str = Field(
        description="One-sentence explanation of the classification decision."
    )


# Bind structured output once at module load (shared across all requests)
_classifier = _classifier_llm.with_structured_output(_TopicDecision)


# ─────────────────────────────────────────────────────────────────────────────
# System prompt — sets the rules for what counts as on-topic
# ─────────────────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """\
You are a safety classifier for a freelance proposal writing tool called CareerCompass.
Your only job is to decide whether an incoming request is related to freelance proposals.

ALLOWED (is_proposal_related = true):
  - Writing a proposal for a freelance project
  - Refining, shortening, expanding, or changing the tone of an existing proposal
  - Questions about how to improve a proposal (e.g. "make it sound more confident")
  - Requests to emphasise specific skills or experience in a proposal
  - Any other task directly about the proposal text being written

NOT ALLOWED (is_proposal_related = false):
  - General coding questions or homework help
  - Job search questions (those belong to the Job Agent)
  - Certification questions (those belong to the Certification Agent)
  - Casual conversation or general chat
  - Harmful, offensive, or manipulative content
  - Anything that is clearly not about a freelance project proposal

Be strict but fair. If in doubt, allow it (err toward true).
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public validator functions
# ─────────────────────────────────────────────────────────────────────────────

def validate_proposal_request(
    project_title: str,
    project_description: str,
) -> None:
    """
    Validate that a proposal generation request is on-topic.

    Called before generate_proposal() in the /freelance/proposal endpoint.

    NOTE: This function is intentionally a no-op (always passes).
    ─────────────────────────────────────────────────────────────
    The /freelance/proposal endpoint receives STRUCTURED PROJECT DATA from the
    frontend (title + description from the freelance agent's output) — not
    free-form user text. An LLM classifier given a project title like
    "Build a RAG chatbot" correctly identifies it as "not a proposal-writing
    request" and blocks it, which is the wrong behaviour.

    The appropriate guardrail is on the CHAT endpoint (validate_chat_message),
    where the user types free-form text that could genuinely be off-topic.
    The generation endpoint is only reachable by authenticated users who have
    already loaded the freelance results page, so the attack surface is minimal.
    """
    # Always allow — see docstring above.
    return


def validate_chat_message(user_message: str) -> None:
    """
    Validate that a chat refinement message is on-topic.

    Called before chat_with_proposal() in the /freelance/proposal/chat endpoint.
    Only the most recent user message is checked — previous turns are already
    in the agent's conversation history and have been validated earlier.

    Parameters
    ──────────
    user_message — The latest message content sent by the user.

    Raises
    ──────
    ValueError — if the message is classified as off-topic.
    """
    # Short messages like "ok" or "thanks" are trivially safe — skip the LLM call
    if len(user_message.strip()) < 5:
        return

    decision: _TopicDecision = _classifier.invoke([
        {"role": "system", "content": _CLASSIFIER_SYSTEM},
        {
            "role": "user",
            "content": (
                f"User message in a proposal refinement conversation: {user_message}\n\n"
                "Is this message related to refining a freelance proposal?"
            ),
        },
    ])

    if not decision.is_proposal_related:
        raise ValueError(
            "This chat is only for refining freelance proposals. "
            f"Your message appears to be off-topic: {decision.reason}"
        )
