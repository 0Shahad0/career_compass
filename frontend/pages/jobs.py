from pathlib import Path
import streamlit as st
import requests
from components.navbar import render_navbar
# ---------------------------------
# Page settings
# ---------------------------------

st.set_page_config(
    page_title="Jobs | CareerCompass",
    page_icon=":material/work:",
    layout="wide"
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"
st.html(ASSETS / "home.css")
logo = ASSETS / "logo.png"
API_BASE = "http://127.0.0.1:8000"


# ---------------------------------
# Auth guard
# ---------------------------------

token = st.session_state.get("token")
if not token:
    st.warning("Please sign in to view your job recommendations.")
    if st.button("Sign in", type="primary"):
        st.switch_page("pages/sign_in.py")
    st.stop()


# =================================
# NAVBAR
# =================================

render_navbar("Jobs")
# =================================
# HEADER
# =================================

with st.container(key="jobs_hero"):

    left, right = st.columns([2, 1], vertical_alignment="center")

    with left:
        st.html('<p class="cc-dashboard-eyebrow">SELECTED FOR YOUR EXPERIENCE</p>')
        st.html('<h1 class="cc-dashboard-title">Jobs for you.</h1>')
        st.html(
            '<p class="cc-dashboard-subtitle">'
            "Opportunities selected based on your career profile."
            "</p>"
        )




# =================================
# PROFILE SNAPSHOT CARD
# =================================

profile = st.session_state.get("profile", {})
personal = profile.get("personal_information", {}) if profile else {}
display_name = personal.get("name", "") or st.session_state.get("user_email", "").split("@")[0].title()
initials = "".join(p[0].upper() for p in display_name.split() if p)[:2] or "U"

experience_list = profile.get("experience", []) if profile else []
current_role = experience_list[0].get("title", "—") if experience_list else "—"

skills_list = [s.get("name", "") for s in (profile.get("skills", []) if profile else [])]
top_3_skills = skills_list[:3]

with st.container(key="jobs_profile_card", border=True):

    left_card, right_card = st.columns([3, 1], vertical_alignment="center")

    with left_card:
        skill_badges = "".join(
            f'<span class="cc-skill-badge">{s}</span>'
            for s in top_3_skills
        )
        st.html(
            f"""
            <div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
                <div class="cc-profile-avatar" style="width:40px;height:40px;font-size:15px;">{initials}</div>
                <div>
                    <div class="cc-profile-value" style="margin:0;">{current_role}</div>
                    <div class="cc-profile-detail" style="margin:0;">
                        {len(experience_list)} role(s) of experience
                    </div>
                </div>
                <div class="cc-skill-badges" style="margin-left:24px;">{skill_badges}</div>
            </div>
            """
        )

    with right_card:
        if st.button("Update profile ↗", key="jobs_update_profile", type="tertiary"):
            st.switch_page("pages/profile_review.py")


# =================================
# FETCH JOBS FROM AGENT
# =================================

if "jobs_results" not in st.session_state:
    with st.spinner("🔍 Finding job opportunities matched to your profile..."):
        try:
            resp = requests.post(
                f"{API_BASE}/api/career/jobs",#LOOK HERE
                json={"query": f"Find jobs matching profile of {current_role}"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=120,
            )

            if resp.status_code == 200:
                data = resp.json()
                st.session_state["jobs_results"] = data.get("jobs", [])
                st.session_state["jobs_analysis"] = data.get("analysis", "")
            else:
                st.session_state["jobs_results"] = []
                st.session_state["jobs_analysis"] = ""
                st.error(f"Agent error (status {resp.status_code}): {resp.text[:200]}")

        except requests.Timeout:
            st.session_state["jobs_results"] = []
            st.session_state["jobs_analysis"] = ""
            st.error("The job agent took too long. Please refresh to try again.")
        except requests.RequestException as e:
            st.session_state["jobs_results"] = []
            st.session_state["jobs_analysis"] = ""
            st.error(f"Could not reach the API: {e}")

jobs = st.session_state.get("jobs_results", [])
analysis = st.session_state.get("jobs_analysis", "")


# =================================
# RESULTS HEADER
# =================================

count_col, note_col = st.columns([2, 2])

with count_col:
    st.caption(
        f"Recommended opportunities · {len(jobs)} role{'s' if len(jobs) != 1 else ''}"
    )

with note_col:
    st.caption("Based on your profile")


# =================================
# REFRESH BUTTON
# =================================

if st.button(
    ":material/refresh: Refresh recommendations",
    key="jobs_refresh",
    type="tertiary"
):
    for key in ["jobs_results", "jobs_analysis"]:
        st.session_state.pop(key, None)
    st.rerun()


# =================================
# JOB CARDS
# =================================

if not jobs:
    st.info(
        "No active job listings were found for this search."
    )
for i, job in enumerate(jobs):
    title = job.get("title", "Untitled Role")
    company = job.get("company", "")
    location = job.get("location", "")
    job_type = (
        job.get("employment_type", "")
        or job.get("job_type", "")
    )

    job_url = (
        job.get("url", "")
        or job.get("job_url", "")
    )

    description = job.get(
        "description",
        ""
    )

    source = job.get(
        "source",
        ""
    )

    is_remote = job.get(
        "is_remote",
        False
    )

    # ---------------------------------
    # Match data
    # ---------------------------------

    match = job.get(
        "match",
        {}
    ) or {}

    score = match.get(
        "score"
    )

    matching_skills = match.get(
        "matching_skills",
        []
    ) or []

    missing_skills = match.get(
        "missing_skills",
        []
    ) or []

    explanation = match.get(
        "explanation",
        ""
    )

    # ---------------------------------
    # Company initial
    # ---------------------------------

    company_initial = (
        company[0].upper()
        if company
        else "J"
    )

    # ---------------------------------
    # Employment label
    # ---------------------------------

    employment_parts = []

    if job_type:
        employment_parts.append(
            str(job_type)
            .replace("_", " ")
            .title()
        )

    if is_remote:
        employment_parts.append(
            "Remote"
        )

    if source:
        employment_parts.append(
            source.title()
        )

    employment_label = (
        " · ".join(employment_parts)
        if employment_parts
        else "Job opportunity"
    )

    # ---------------------------------
    # Description snippet
    # ---------------------------------

    if description:
        snippet = (
            description
            .replace("\n", " ")
            .strip()
        )

        if len(snippet) > 220:
            snippet = (
                snippet[:220].strip()
                + "…"
            )
    else:
        snippet = ""


    # ---------------------------------
    # Job card
    # ---------------------------------

    with st.container(
        key=f"job_card_{i}",
        border=True
    ):

        # =============================
        # Header
        # =============================

        top_left, top_right = st.columns(
            [5, 1],
            vertical_alignment="top"
        )

        with top_left:
            st.html(
                f"""
                <div style="
                    display:flex;
                    align-items:flex-start;
                    gap:14px;
                ">
                    <div class="cc-job-company-icon">
                        {company_initial}
                    </div>
                    <div>
                        <div
                            class="cc-profile-value"
                            style="
                                font-size:18px;
                                margin:0;
                            "
                        >
                            {title}
                        </div>

                        <div
                            class="cc-profile-detail"
                            style="
                                margin:3px 0 0;
                            "
                        >
                            {company}
                            {
                                " · " + location
                                if location
                                else ""
                            }
                        </div>
                    </div>
                </div>
                """
            )

        with top_right:
            if score is not None:
                st.html(
                    f'<div class="cc-match-badge">{score}% Match</div>'
                )
            else:
                st.html(
                    '<div class="cc-match-badge">Match</div>'
                )

            with st.popover("Tailor CV", use_container_width=True):

                st.markdown("### Tailor Your CV")

                st.caption(
                    f"{title} · {company}"
                )

                if not description:
                    st.warning(
                        "This job does not provide a description, "
                        "so tailoring suggestions may be limited."
                    )

                if st.button(
                    "Generate Suggestions",
                    key=f"generate_tailor_{i}",
                    type="primary",
                    use_container_width=True,
                ):

                    with st.spinner("Analyzing your CV against this job..."):

                        try:
                            tailor_resp = requests.post(
                                f"{API_BASE}/api/career/jobs/tailor-cv",
                                json={
                                    "job_title": title,
                                    "job_description": description or "",
                                },
                                headers={
                                    "Authorization": f"Bearer {token}"
                                },
                                timeout=120,
                            )

                            if tailor_resp.status_code == 200:

                                tailor_result = tailor_resp.json()

                                st.session_state[
                                    f"tailor_result_{i}"
                                ] = tailor_result

                            else:
                                st.error(
                                    f"Tailoring failed "
                                    f"(status {tailor_resp.status_code}): "
                                    f"{tailor_resp.text}"
                                )

                        except requests.RequestException as e:
                            st.error(
                                f"Could not reach the API: {e}"
                            )

                tailor_result = st.session_state.get(
                    f"tailor_result_{i}"
                )

                if tailor_result:

                    st.divider()

                    st.metric(
                        "ATS Match",
                        f"{tailor_result.get('ats_match', 0)}%"
                    )

                    keywords = tailor_result.get(
                        "keywords_to_emphasize",
                        []
                    )

                    if keywords:
                        st.markdown("**Keywords to emphasize**")

                        st.write(
                            ", ".join(keywords)
                        )

                    missing_keywords = tailor_result.get(
                        "missing_keywords",
                        []
                    )

                    if missing_keywords:
                        st.markdown("**Missing keywords**")

                        st.write(
                            ", ".join(missing_keywords)
                        )

                    suggestions = tailor_result.get(
                        "suggestions",
                        []
                    )

                    if suggestions:
                        st.markdown("**Suggested changes**")

                        for suggestion in suggestions:

                            st.markdown(
                                f"**{suggestion.get('category', 'Suggestion').title()}**"
                            )

                            if suggestion.get("current"):
                                st.caption(
                                    f"Current: {suggestion['current']}"
                                )

                            st.write(
                                suggestion.get("suggested", "")
                            )

                            st.caption(
                                suggestion.get("reason", "")
                            )

        # =============================
        # Description
        # =============================

        if snippet:
            st.write(snippet)

        # =============================
        # Matching skills
        # =============================

        if matching_skills:

            badges = "".join(
                f'''
                <span class="cc-skill-badge">
                    {skill}
                </span>
                '''
                for skill in matching_skills[:5]
            )

            st.html(
                f'''
                <div
                    class="cc-skill-badges"
                    style="margin:8px 0;"
                >
                    {badges}
                </div>
                '''
            )

        # =============================
        # Why it matches
        # =============================

        if explanation:

            st.html(
                f"""
                <div class="cc-why-matches">

                    <div class="cc-why-title">
                        Why it matches
                    </div>

                    <div class="cc-why-text">
                        {explanation}
                    </div>

                </div>
                """
            )

        # =============================
        # Skill gaps
        # =============================

        if missing_skills:

            missing_text = ", ".join(
                str(skill)
                for skill in missing_skills[:5]
            )

            st.html(
                f"""
                <div
                    style="
                        margin-top:10px;
                        padding:10px 12px;
                        border-radius:8px;
                        background:#fafafa;
                    "
                >

                    <div
                        style="
                            font-weight:600;
                            margin-bottom:4px;
                        "
                    >
                        Skill gaps
                    </div>

                    <div
                        style="
                            font-size:14px;
                        "
                    >
                        {missing_text}
                    </div>

                </div>
                """
            )

        # =============================
        # Footer
        # =============================

        footer_left, footer_right = st.columns(
            [2, 1],
            vertical_alignment="center"
        )

        with footer_left:

            st.caption(
                employment_label
            )

        with footer_right:

            if job_url:
                with st.container(key=f"view_job_button_{i}"):

                   st.link_button(
                    "View Job ↗",
                    url=str(job_url),
                    type="primary",
                    use_container_width=True
                )

            else:

                st.button(
                    "View Job ↗",
                    key=f"job_view_{i}",
                    type="primary",
                    use_container_width=True,
                    disabled=True
                    )