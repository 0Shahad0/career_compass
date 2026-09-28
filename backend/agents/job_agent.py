from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from langsmith import traceable

from backend.graph.state import CareerState
from backend.config import settings
from backend.tools.job_search import search_jobs
from backend.tools.onet import get_occupation_information
from backend.guardrails.job_guardrails import validate_job_analysis
from backend.tools.resume import get_required_skills
from backend.schemas.career_response import (
    JobOpportunity,
    MatchDetails,
)
from pydantic import BaseModel, Field
import re
from difflib import SequenceMatcher


# ---------------------------------
# Structured output for job matching
# ---------------------------------

class JobMatchResult(BaseModel):
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    explanation: str


class JobAgentOutput(BaseModel):
    jobs: list[JobOpportunity] = Field(default_factory=list)


# ---------------------------------
# LLM
# ---------------------------------

llm = ChatOpenAI(
    model="gpt-5.4-mini",
    temperature=0,
    api_key=settings.openai_api_key,
)

llm_with_tools = llm.bind_tools([
    search_jobs,
    get_occupation_information,
    get_required_skills,
])


# ---------------------------------
# Helpers
# ---------------------------------

def clean_job_url(url: str) -> str:
    """
    Convert JobSpy markdown-style URLs into plain URLs.

    Example:
    [https://example.com/job](https://example.com/job)

    becomes:
    https://example.com/job
    """

    if not url:
        return ""

    url = str(url).strip()

    markdown_match = re.match(
        r"^\[.*?\]\((https?://[^)]+)\)$",
        url,
    )

    if markdown_match:
        return markdown_match.group(1)

    return url


def run_job_search(
    search_term: str,
    location: str,
) -> list[dict]:
    """
    Run JobSpy safely and return real job listings.
    """

    try:
        result = search_jobs.invoke(
            {
                "search_term": search_term,
                "location": location,
            }
        )

        if isinstance(result, list):
            return result

    except Exception as exc:
        print(
            f"[JOB SEARCH ERROR] "
            f"{search_term} | {location} | {exc}"
        )
    return []

def deduplicate_jobs(jobs: list[dict]) -> list[dict]:
    """
    Remove duplicate jobs using the original job URL.
    """
    unique_jobs = []
    seen_urls = set()

    for job in jobs:

        if not isinstance(job, dict):
            continue

        raw_url = job.get("job_url", "")
        job_url = clean_job_url(raw_url)

        if not job_url:
            continue

        if job_url in seen_urls:
            continue

        seen_urls.add(job_url)

        cleaned_job = dict(job)
        cleaned_job["job_url"] = job_url

        unique_jobs.append(cleaned_job)

    return unique_jobs

def normalize_text(value: str | None) -> str:
    """
    Normalize text for generic matching.
    """
    if not value:
        return ""

    return " ".join(
        str(value).lower().strip().split()
    )

def skill_name(skill) -> str:
    """
    Get the skill name from either a string
    or a Pydantic skill object.
    """
    if isinstance(skill, str):
        return skill.strip()

    return (
        getattr(skill, "name", "") or ""
    ).strip()

def calculate_role_relevance(
    job_title: str,
    user_experience: list[str],
) -> float:
    """
    Calculate generic role relevance using
    title similarity and meaningful word overlap.

    This function is domain-agnostic and does not
    rely on predefined job-role categories.

    Returns a value between 0 and 1.
    """
    if not job_title or not user_experience:
        return 0.0

    normalized_job_title = normalize_text(job_title)

    scores = []

    for experience_title in user_experience:
        normalized_experience = normalize_text(
            experience_title
        )

        if not normalized_experience:
            continue

        # Direct title similarity
        similarity = SequenceMatcher(
            None,
            normalized_job_title,
            normalized_experience,
        ).ratio()

        # Word overlap
        job_words = set(
            normalized_job_title.split()
        )

        experience_words = set(
            normalized_experience.split()
        )

        if job_words and experience_words:
            overlap = len(
                job_words & experience_words
            ) / len(job_words)
        else:
            overlap = 0.0

        # Combine both signals
        combined_score = (
            similarity * 0.6
            + overlap * 0.4
        )

        scores.append(
            min(combined_score, 1.0)
        )

    return max(scores, default=0.0)

def calculate_location_relevance(
    user_location: str,
    job_location: str,
    is_remote: bool,
) -> float:
    """
    Calculate generic location relevance.

    Returns a value between 0 and 1.

    Priority:
    1. Same city
    2. Remote
    3. Same country
    4. Other location
    """

    user_location = normalize_text(
        user_location
    )

    job_location = normalize_text(
        job_location
    )

    if not user_location:
        return 0.0

    if is_remote or "remote" in job_location:
        return 0.75

    if not job_location:
        return 0.0

    # Use the first location component as the
    # user's city.
    user_city = (
        user_location
        .split(",")[0]
        .strip()
    )

    if (
        user_city
        and user_city in job_location
    ):
        return 1.0

    # Generic Saudi Arabia detection.
    saudi_terms = {
        "saudi arabia",
        "ksa",
        "kingdom of saudi arabia",
        "saudi",
    }

    user_is_saudi = any(
        term in user_location
        for term in saudi_terms
    )

    job_is_saudi = any(
        term in job_location
        for term in saudi_terms
    )

    if user_is_saudi and job_is_saudi:
        return 0.5

    return 0.25

def calculate_match_score(
    job: dict,
    user_skills: list[str],
    user_experience: list[str],
    user_location: str,
) -> int:
    """
    Calculate a generic overall job match score.
    Returns a value between 0 and 100.
    """

    title = str(
        job.get("title", "")
    )

    description = str(
        job.get("description", "")
    )

    job_text = normalize_text(
        f"{title} {description}"
    )

    # ---------------------------------
    # Skills
    # ---------------------------------

    normalized_user_skills = [
        normalize_text(skill)
        for skill in user_skills
        if normalize_text(skill)
    ]

    if normalized_user_skills:
        matching_skill_count = sum(
            1
            for skill in normalized_user_skills
            if skill in job_text
        )

        skill_relevance = (
            matching_skill_count
            / len(normalized_user_skills)
        )
    else:
        skill_relevance = 0.0

    # ---------------------------------
    # Role
    # ---------------------------------

    role_relevance = calculate_role_relevance(
        job_title=title,
        user_experience=user_experience,
    )

    # ---------------------------------
    # Location
    # ---------------------------------

    location_relevance = (
        calculate_location_relevance(
            user_location=user_location,
            job_location=str(
                job.get("location", "")
            ),
            is_remote=bool(
                job.get("is_remote", False)
            ),
        )
    )

    # ---------------------------------
    # Overall score
    # ---------------------------------

    overall_score = round(
        (skill_relevance * 50)
        + (role_relevance * 30)
        + (location_relevance * 20)
    )

    return max(
        0,
        min(100, overall_score),
    )

# ---------------------------------
# Job Agent
# ---------------------------------
@traceable(name="job_agent", tags=["job-agent"])
def job_agent(state: CareerState):

    user_profile = state.get("user_profile")

    if not user_profile:
        name = ""
        education = []
        experience = []
        skills = []
        location = ""
    else:
        name = getattr(
            user_profile.personal_information,
            "name",
            "",
        )

        location = getattr(
            user_profile.personal_information,
            "location",
            "",
        )

        education = user_profile.education
        experience = user_profile.experience
        skills = user_profile.skills

    query = state.get(
        "query",
        "Find jobs that match my profile",
    )

    # ---------------------------------
    # Main agent prompt
    # ---------------------------------

    prompt = f"""
You are the Job Agent in Career Compass.

Your job is to find REAL job opportunities and evaluate
how well they match the user's profile.

USER PROFILE
------------
Name: {name}
Education: {education}
Experience: {experience}
Skills: {skills}
Location: {location}

USER REQUEST
------------
{query}

INSTRUCTIONS
------------

1. Identify the target job role from the user's request
   and profile.

2. Use the search_jobs tool to find REAL job listings.

3. Search using a concise job role such as:
   - AI Engineer
   - Machine Learning Engineer
   - Data Scientist
   - Software Engineer

4. Use the user's location when available.

5. Use O*NET to understand the identified occupation.

6. Use the Resume tool only when the retrieved title
   is clearly relevant to the target role.

7. Do NOT use the user's skills as the job title.

8. Do NOT invent job opportunities.

9. A job is considered real only if it comes from the
   search_jobs tool and has a real job URL.

10. If no jobs are found in the user's immediate location,
    the system may broaden the search to Saudi Arabia
    and major Saudi cities.

11. For each REAL job returned by search_jobs, evaluate
    the job against the user's skills and experience.

12. Identify:
    - matching skills
    - missing skills
    - a short explanation of why the job matches

13. Keep each explanation concise and user-focused.

14. Do not write a long general career report.

15. Do not generate alternative job titles as if they
    were available job listings.

The final result must focus on REAL JOB OPPORTUNITIES.
"""

    messages = [
        HumanMessage(content=prompt)
    ]

    # ---------------------------------
    # First LLM call
    # ---------------------------------

    response = llm_with_tools.invoke(messages)

    jobs = []
    search_term = ""

    # ---------------------------------
    # Execute requested tools
    # ---------------------------------

    if response.tool_calls:

        messages.append(response)

        for tool_call in response.tool_calls:

            tool_name = tool_call["name"]

            if tool_name == "search_jobs":

                tool_args = tool_call["args"]

                search_term = (
                    tool_args.get("search_term")
                    or search_term
                )

                tool_result = search_jobs.invoke(
                    tool_args
                )

                if isinstance(tool_result, list):
                    jobs.extend(tool_result)

            elif tool_name == "get_occupation_information":

                tool_result = get_occupation_information.invoke(
                    tool_call["args"]
                )

            elif tool_name == "get_required_skills":

                tool_result = get_required_skills.invoke(
                    tool_call["args"]
                )

            else:
                continue

            messages.append(
                ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call["id"],
                )
            )

    # ---------------------------------
    # Clean first search
    # ---------------------------------

    jobs = deduplicate_jobs(jobs)

    # ---------------------------------
    # FALLBACK SEARCH
    # ---------------------------------

    if not jobs and search_term:

        original_location = (
            str(location).strip()
            if location
            else ""
        )

        fallback_locations = []

        # If no jobs are found in the user's
        # exact location, broaden only to Saudi Arabia.
        if original_location.lower() not in {
            "saudi arabia",
            "ksa",
            "kingdom of saudi arabia",
        }:
            fallback_locations.append(
                "Saudi Arabia"
            )
        for fallback_location in fallback_locations:

            print(
                f"[JOB SEARCH FALLBACK] "
                f"{search_term} | {fallback_location}"
            )

            fallback_jobs = run_job_search(
                search_term=search_term,
                location=fallback_location,
            )

            jobs.extend(fallback_jobs)

            jobs = deduplicate_jobs(jobs)

            if jobs:
                break

    # ---------------------------------
    # No real jobs found
    # ---------------------------------

    if not jobs:

        return {
            "job_analysis": (
                "No active job listings were found "
                "for this search."
            ),
            "jobs": [],
        }

    # Keep the first 10 real opportunities.
    jobs = jobs[:10]

    # ---------------------------------
    # User profile data
    # ---------------------------------

    user_skills = [
        getattr(skill, "name", "")
        for skill in skills
        if getattr(skill, "name", "")
    ]

    user_experience = [
        getattr(exp, "title", "")
        for exp in experience
        if getattr(exp, "title", "")
    ]

    # ---------------------------------
    # Match each real job
    # ---------------------------------

    matched_jobs = []

    for job in jobs:

        title = str(
            job.get("title", "")
        ).strip()

        company = str(
            job.get("company", "")
        ).strip()

        job_location = str(
            job.get("location", "")
        ).strip()

        job_type = str(
            job.get("job_type", "")
        ).strip()

        source = str(
            job.get("site", "")
        ).strip()

        job_url = clean_job_url(
            job.get("job_url", "")
        )

        description = str(
            job.get("description", "")
        ).strip()

        is_remote = bool(
            job.get("is_remote", False)
        )

        date_posted = job.get(
            "date_posted"
        )

        # ---------------------------------
        # Match analysis
        # ---------------------------------

        match_prompt = f"""
Evaluate this REAL job opportunity against
the user's profile.

USER SKILLS:
{user_skills}

USER EXPERIENCE:
{user_experience}

JOB TITLE:
{title}

COMPANY:
{company}

JOB LOCATION:
{job_location}

JOB TYPE:
{job_type}

JOB DESCRIPTION:
{description[:5000]}

Return:
1. matching_skills
2. missing_skills
3. a short explanation

Rules:
- Only use skills supported by the user profile
  or the job description.
- Do not invent user experience.
- Keep the explanation to 1-2 sentences.
- Focus on useful information for the user.
"""

        try:
            structured_match = llm.with_structured_output(
                JobMatchResult
            )
            match_result = structured_match.invoke(
                [
                    HumanMessage(
                        content=match_prompt
                    )
                ]
            )
            # Calculate the numerical score
            # independently from the LLM.
            overall_score = calculate_match_score(
                job=job,
                user_skills=user_skills,
                user_experience=user_experience,
                user_location=str(location),
            )

            match = MatchDetails(
                score=overall_score,
                matching_skills=(
                    match_result.matching_skills
                ),
                missing_skills=(
                    match_result.missing_skills
                ),
                explanation=(
                    match_result.explanation
                ),
            )

        except Exception as exc:

            print(
                f"[JOB MATCH ERROR] "
                f"{title}: {exc}"
            )

            match = MatchDetails(
                score=None,
                matching_skills=[],
                missing_skills=[],
                explanation=(
                    "This opportunity was found "
                    "from the job search source."
                ),
            )

        # ---------------------------------
        # Build frontend-safe job
        # ---------------------------------

        matched_jobs.append(
            JobOpportunity(
                title=title or "Untitled Role",
                company=company or None,
                location=job_location or None,
                url=job_url or None,
                employment_type=(
                    job_type or None
                ),
                source=(
                    source or "Job Search"
                ),
                is_remote=is_remote,
                date_posted=(
                    str(date_posted)
                    if date_posted
                    else None
                ),
                description=(
                    description or None
                ),
                match=match,
            )
        )

    # ---------------------------------
    # Final response
    # ---------------------------------

    # Sort jobs from highest match score to lowest
    matched_jobs.sort(
        key=lambda job: (
            job.match.score
            if job.match.score is not None
            else -1
        ),
        reverse=True,
    )
    job_analysis = (
        f"Found {len(matched_jobs)} "
        f"active job listing(s)."
    )

    validated_analysis = validate_job_analysis(
        job_analysis
    )

    return {
        "job_analysis": validated_analysis,
        "jobs": [
            job.model_dump()
            for job in matched_jobs
        ],
    }