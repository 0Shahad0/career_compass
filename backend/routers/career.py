"""
Dedicated per-page career endpoints.
Each endpoint calls the relevant agent directly using the user's stored profile.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlmodel import Session

from backend.database.database import get_session
from backend.database.crud import get_user, get_profile_review
from backend.security import decode_access_token
from backend.tools.certification_search import search_certifications

logger = logging.getLogger(__name__)

from backend.agents.job_agent import job_agent
from backend.agents.freelance_agent import freelance_agent
from backend.agents.certification_agent2 import (
    recommend_certifications,
    prepare_selected_certification,
)
# Import the proposal agent functions.
# generate_proposal() creates the first draft; chat_with_proposal()
# handles follow-up refinement messages from the user.
from backend.agents.proposal_agent import generate_proposal, chat_with_proposal

# Import proposal guardrails.
# validate_proposal_request() checks the project title/description before generation.
# validate_chat_message() checks every new user message before the refinement call.
# Both raise ValueError with a user-facing reason if the request is off-topic.
from backend.guardrails.proposal_guardrails import (
    validate_proposal_request,
    validate_chat_message,
)
from backend.schemas.career_response import CVTailoringResponse

router = APIRouter(
    prefix="/api/career",
    tags=["Career Agents"],
)


# --------------------------------------------------
# Auth helper
# --------------------------------------------------

def get_current_user_id(
    authorization: Optional[str] = Header(default=None),
) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# --------------------------------------------------
# Helper: load & convert profile from DB to agent format
# --------------------------------------------------

from backend.schemas.profile import UserProfile


def load_agent_profile(
    user_id: int,
    session: Session,
) -> UserProfile:
    """
    Load the user's approved ProfileReview JSON and convert it to
    the UserProfile Pydantic object that the career agents expect.
    """
    review = get_profile_review(session, user_id)

    if not review or not review.profile_data:
        return UserProfile()

    try:
        # The agents now expect the full UserProfile object
        return UserProfile.model_validate_json(review.profile_data)
    except Exception:
        return UserProfile()


# ==================================================
# JOBS endpoint
# ==================================================

class JobsRequest(BaseModel):
    query: str = "Find jobs that match my profile"


@router.post("/jobs")
def get_job_recommendations(
    request: JobsRequest = JobsRequest(),
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    user = get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = load_agent_profile(user_id, session)

    state = {
        "user_id": str(user_id),
        "query": request.query,
        "user_profile": profile,
    }

    result = job_agent(state)

    return {
        "jobs": result.get("jobs", []),
        "analysis": result.get("job_analysis", ""),
    }


# ==================================================
# CV TAILORING endpoint
# ==================================================

class CVTailoringRequest(BaseModel):
    job_title: str
    job_description: str


@router.post("/jobs/tailor-cv")
def tailor_cv_for_job(
    request: CVTailoringRequest,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    user = get_user(session, user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    profile = load_agent_profile(user_id,session,)

    # CV tailoring assistant
    from openai import OpenAI
    client = OpenAI()
    tailoring_prompt = f"""
    You are a CV tailoring assistant.
    Analyze the user's existing profile against the target job.

    TARGET JOB:
    Title: {request.job_title}

    Description:
    {request.job_description}

    USER PROFILE:
    {json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)}

    Your task:
    1. Estimate an ATS match score from 0 to 100.
    2. Suggest only realistic changes to the existing CV.
    3. Focus mainly on:
    - Professional title
    - Professional summary
    - Skills to emphasize
    - Experience/projects to emphasize
    4. Do NOT invent skills, experience, education, certifications, or achievements.
    5. Only recommend keywords that are supported by the user's existing profile.
    6. Never change factual personal information such as graduation status, degree, GPA, dates, employers, job titles, or certifications. Preserve the user's actual profile facts exactly.
    7. Keep suggestions concise and practical.

    Return ONLY valid JSON matching this structure:
    {{
        "ats_match": 0,
        "job_title": "{request.job_title}",
        "suggestions": [
            {{
                "category": "summary",
                "current": "...",
                "suggested": "...",
                "reason": "..."
            }}
        ],
        "keywords_to_emphasize": [],
        "missing_keywords": []
    }}
    """

    response = client.responses.create(
        model="gpt-5.6",
        input=tailoring_prompt,
    )

    result = json.loads(response.output_text)

    return CVTailoringResponse.model_validate(result)


# ==================================================
# FREELANCE endpoint
# ==================================================

class FreelanceRequest(BaseModel):
    query: str = "Find freelance projects that match my skills"


@router.post("/freelance")
def get_freelance_recommendations(
    request: FreelanceRequest = FreelanceRequest(),
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    user = get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = load_agent_profile(user_id, session)

    state = {
        "user_id": str(user_id),
        "query": request.query,
        "user_profile": profile,
    }

    result = freelance_agent(state)

    # Convert Pydantic models to dicts for consistent JSON serialization.
    # FastAPI can serialize Pydantic objects, but being explicit avoids
    # edge cases where nested models might not serialize as expected.
    raw_projects = result.get("freelance_projects", [])
    projects = [
        p.model_dump() if hasattr(p, "model_dump") else p
        for p in raw_projects
    ]

    print(f"\n[DEBUG] Freelance endpoint returning {len(projects)} projects")
    if projects:
        print(f"[DEBUG] First project keys: {list(projects[0].keys())}")

    return {
        "freelance_projects": projects,
        "analysis": result.get("freelance_analysis", ""),
    }


# ==================================================
# PROPOSAL endpoint — generate the first draft
# ==================================================

class ProposalRequest(BaseModel):
    """
    The frontend sends the project details it already has from the
    freelance cards — the agent then uses these plus the user profile
    to write a personalized proposal.
    """
    project_title: str
    project_description: str
    budget_or_rate: str | None = None
    matching_skills: list[str] = []
    missing_skills: list[str] = []


@router.post("/freelance/proposal")
def get_proposal(
    request: ProposalRequest,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    """
    Generate a personalized first-draft proposal for a specific project.

    Called when the user clicks "View Proposal" on a freelance card.
    Only runs once per project (the frontend caches the result in
    session state), so latency here is acceptable.
    """
    user = get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ── Guardrail: block off-topic requests before touching the LLM ──────────
    # This runs a fast LLM classifier (gpt-4o-mini) that verifies the project
    # title and description are genuinely about a freelance project proposal.
    # Off-topic requests (homework, general chat, etc.) are rejected here with
    # HTTP 422 so the expensive proposal agent never runs.
    try:
        validate_proposal_request(
            project_title=request.project_title,
            project_description=request.project_description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Load the user's full profile — this is the same profile object
    # used by all other agents. It contains skills, experience, projects.
    profile = load_agent_profile(user_id, session)

    # Call the proposal agent functions directly.
    proposal = generate_proposal(
        profile=profile,
        project_title=request.project_title,
        project_description=request.project_description,
        budget_or_rate=request.budget_or_rate,
        matching_skills=request.matching_skills,
        missing_skills=request.missing_skills,
    )

    return {"proposal": proposal}


# ==================================================
# PROPOSAL CHAT endpoint — refine the proposal
# ==================================================

class ChatMessage(BaseModel):
    """A single message in the conversation history."""
    role: str
    content: str


class ProposalChatRequest(BaseModel):
    """
    The frontend sends the full conversation history on every turn.

    This "stateless" design means the backend doesn't need to store
    any session state — all history lives in the Streamlit session_state.
    """
    project_title: str
    project_description: str
    # The complete conversation so far, including the first AI proposal.
    # Example: [{"role": "assistant", "content": "Dear..."},
    #           {"role": "user",      "content": "make it shorter"}]
    messages: list[ChatMessage]


@router.post("/freelance/proposal/chat")
def refine_proposal(
    request: ProposalChatRequest,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    """
    Continue the proposal refinement conversation.

    Called every time the user sends a follow-up message in the chat
    window (e.g. "make it shorter", "focus on my Python experience").
    Always receives the full conversation history for proper context.
    """
    user = get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ── Guardrail: check the latest user message before refinement ────────────
    # We only validate the last user message, not the entire history.
    # Earlier turns were already validated when they were sent.
    # If the user tries to use the chat for off-topic purposes (e.g. asking
    # general questions or injecting unrelated requests), we block here.
    last_user_message = next(
        (msg.content for msg in reversed(request.messages) if msg.role == "user"),
        "",
    )
    try:
        validate_chat_message(last_user_message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    profile = load_agent_profile(user_id, session)

    messages = [
        {"role": message.role, "content": message.content}
        for message in request.messages
    ]

    response = chat_with_proposal(
        profile=profile,
        project_title=request.project_title,
        project_description=request.project_description,
        messages=messages,
    )

    return {"reply": response}


# ==================================================
# CERTIFICATIONS endpoint — Stage 1: Recommendations
# ==================================================

@router.post("/certifications")
def get_certification_recommendations(
    offset: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=10,
    ),
    user_id: int = Depends(
        get_current_user_id
    ),
    session: Session = Depends(
        get_session
    ),
):
    user = get_user(
        session,
        user_id,
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    profile = load_agent_profile(
        user_id,
        session,
    )

    state = {
        "user_id": str(user_id),
        "query": (
            "Recommend certifications "
            "based on my full professional profile"
        ),
        "user_profile": profile,
        "offset": offset,
        "limit": limit,
    }

    result = recommend_certifications(
        state
    )

    return {
        "recommendations":
            result.get(
                "certifications",
                [],
            ),
        "pagination":
            result.get(
                "pagination",
                {},
            ),
        "analysis":
            result.get(
                "certification_analysis",
                "",
            ),
    }


@router.get("/certifications/search")
def search_any_certification(
    query: str = Query(min_length=1, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=10),
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    if not get_user(session, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    query = query.strip()
    if not query:
        raise HTTPException(
            status_code=422,
            detail="Enter a certification search.",
        )

    try:
        # Manual search uses no profile, recommendation filter, or LLM.
        matches = search_certifications(query, include_retired=True)
    except Exception:
        logger.exception("Manual certification search failed.")
        raise HTTPException(
            status_code=503,
            detail="Certification search is temporarily unavailable.",
        )

    results = []
    seen = set()

    for exam in matches:
        exam_id = exam.get("exam_id")
        if (
            not isinstance(exam_id, str)
            or not exam_id.strip()
            or exam_id in seen
        ):
            continue

        seen.add(exam_id)
        results.append({
            "exam_id": exam_id,
            "name": (
                exam.get("exam_name")
                or exam.get("certification_name")
                or "Certification"
            ),
            "provider": (
                exam.get("certifying_body")
                or "Not available in the dataset."
            ),
            "exam_code": exam.get("exam_code"),
            "url": exam.get("source_url"),
            "lifecycle_status": exam.get("lifecycle_status"),
        })

    page = results[offset:offset + limit]
    next_offset = offset + len(page)
    has_more = bool(page) and next_offset < len(results)

    return {
        "certifications": page,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": len(results),
            "returned": len(page),
            "has_more": has_more,
            "next_offset": next_offset if has_more else None,
        },
    }


# ==================================================
# CERTIFICATIONS/STUDY-PLAN — Stage 2: Study plan
# ==================================================

class StudyPlanRequest(BaseModel):
    selected_certification: str
    current_level: str = "Intermediate"
    exam_date: str  # YYYY-MM-DD


@router.post("/certifications/study-plan")
def get_study_plan(
    request: StudyPlanRequest,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    user = get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = load_agent_profile(user_id, session)

    state = {
        "user_id": str(user_id),
        "query": f"Create a study plan for {request.selected_certification}",
        "user_profile": profile,
        "selected_certification": request.selected_certification,
        "current_level": request.current_level,
        "exam_date": request.exam_date,
    }

    result = prepare_selected_certification(state)

    return {
        "study_plan": result.get("certification_analysis", ""),
    }