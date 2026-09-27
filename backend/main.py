# ─────────────────────────────────────────────────────────────────
# Suppress a harmless Pydantic serialization warning.
#
# LangChain's with_structured_output() stores parsed Pydantic models
# in AIMessage.parsed, which is internally typed as Optional[None].
# Pydantic sees a real model where it expected None and emits:
#
#   PydanticSerializationUnexpectedValue(Expected `none` …)
#
# The warning is harmless — the data is always parsed correctly.
# We filter it here (before any agent imports) so it's active
# process-wide for every agent that uses with_structured_output().
# ─────────────────────────────────────────────────────────────────
import warnings
warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module=r"pydantic\.main",
)

from fastapi import FastAPI, Depends
from sqlmodel import Session

from backend.routers.auth import router as auth_router
from backend.routers.portfolio import router as portfolio_router
from backend.routers.career import router as career_router

# Resume upload and CV processing routes
from backend.routers.resume import router as resume_router

from backend.database.database import (
    create_db_and_tables,
    get_session,
)

from backend.database.crud import (
    create_user,
    get_user,
    get_user_profile,
)
from backend.schemas.career import (
    CareerRequest,
    UserProfileRequest
    )

from backend.graph.graph import career_graph


app = FastAPI(
    title="Career Compass API",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(portfolio_router)
app.include_router(career_router)
app.include_router(resume_router)

@app.on_event("startup")
def startup():
    create_db_and_tables()


@app.get("/")
def root():
    return {
        "message": "Career Compass API is running"
    }


@app.post("/api/career")
def career_assistant(
    request: CareerRequest,
    session: Session = Depends(get_session),
):
    user = get_user(
        session=session,
        user_id=request.user_id,
    )

    if not user:
        return {
            "error": "User not found"
        }

    profile = get_user_profile(
        session=session,
        user_id=request.user_id,
    )

    user_profile = {
        "name": profile.name if profile else "",
        "education": profile.education if profile else "",
        "experience": [],
        "skills": [],
        "interests": profile.interests if profile else "",
        "location": profile.location if profile else "",
    }

    user = get_user(
        session=session,
        user_id=request.user_id
    )

    if not user:
        return {
            "error": "User not found"
        }

    user_profile = {
        "name": user.name,
        "education": user.education or "",
        "experience": user.experience.split(",") if user.experience else [],
        "skills": user.skills.split(",") if user.skills else [],
        "interests": user.interests.split(",") if user.interests else [],
        "location": user.location or ""
    }

    initial_state = {
        "user_id": request.user_id,
        "query": request.query,
        "user_profile": user_profile,
    }

    result = career_graph.invoke(initial_state)
    print("\n================ GRAPH RESULT ================")
    print(result)
    print("================================================\n")

    return {
    "response": result.get("final_response", ""),
    "jobs": result.get("jobs", []),
    "certifications": result.get("certifications", []),
    "freelance_projects": result.get("freelance_projects", []),
    }

    # return {
    #     "response": result.get("final_response", ""),
    #     "jobs": result.get("jobs", []),
    #     "certifications": result.get("certifications", []),
    #     "freelance_projects": result.get("freelance_projects", []),
    # }