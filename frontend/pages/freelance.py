from pathlib import Path
import os
import requests
import streamlit as st
from components.navbar import render_navbar

# =================================
# Page settings
# =================================

st.set_page_config(
    page_title="Freelance | CareerCompass",
    page_icon=":material/hub:",
    layout="wide"
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"
st.html(ASSETS / "home.css")
logo = ASSETS / "logo.png"
API_BASE = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
)

# =================================
# Auth guard
# =================================

token = st.session_state.get("token")
if not token:
    st.warning("Please sign in to view your freelance recommendations.")
    if st.button("Sign in", type="primary"):
        st.switch_page("pages/sign_in.py")
    st.stop()
    
# =================================
# NAVBAR
# =================================

render_navbar("Freelance")

# =================================
# HEADER
# =================================

with st.container(key="freelance_hero"):

    left = st.container()

    with left:
        st.html('<p class="cc-dashboard-eyebrow">SELECTED FOR YOUR EXPERIENCE</p>')
        st.html('<h1 class="cc-dashboard-title">Freelance projects for you.</h1>')
        st.html(
            '<p class="cc-dashboard-subtitle">'
            "Projects selected based on your skills and professional experience."
            "</p>"
        )


# =================================
# FETCH FREELANCE PROJECTS FROM API
# =================================

# We extract the profile from session state so the frontend can show
# the user''s name and skills without another API call.
profile = st.session_state.get("profile", {})
skills_list = [s.get("name", "") for s in (profile.get("skills", []) if profile else [])]
personal = profile.get("personal_information", {}) if profile else {}
display_name = personal.get("name", "") or st.session_state.get("user_email", "").split("@")[0].title()

# Only fetch if we do not already have results cached in session state.
# Once fetched, the list stays until the user clicks "Refresh projects".
if "freelance_results" not in st.session_state:
    with st.spinner("Finding freelance projects matched to your skills..."):
        try:
            resp = requests.post(
                f"{API_BASE}/api/career/freelance",
                json={"query": "Find freelance projects that match my skills"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=120,
            )

            if resp.status_code == 200:
                data = resp.json()
                st.session_state["freelance_results"] = data.get("freelance_projects", [])
                st.session_state["freelance_analysis"] = data.get("analysis", "")
                st.toast(f"Found {len(st.session_state['freelance_results'])} projects for you")
            else:
                st.session_state["freelance_results"] = []
                st.session_state["freelance_analysis"] = ""
                st.error(f"Agent error (status {resp.status_code})")

        except requests.Timeout:
            st.session_state["freelance_results"] = []
            st.session_state["freelance_analysis"] = ""
            st.error("The freelance agent took too long. Please refresh.")

        except requests.RequestException as e:
            st.session_state["freelance_results"] = []
            st.session_state["freelance_analysis"] = ""
            st.error(f"Could not reach the API: {e}")


projects = st.session_state.get("freelance_results", [])
analysis = st.session_state.get("freelance_analysis", "")


# Refresh button clears the cached projects AND all cached proposals
# so everything is fetched fresh on the next page load.
if st.button(
    ":material/refresh: Refresh projects",
    key="fl_refresh",
    type="tertiary"
):
    # Clear project list, analysis, and every cached proposal/chat
    keys_to_clear = [k for k in st.session_state if k.startswith("freelance")]
    keys_to_clear += [k for k in st.session_state if k.startswith("proposal_")]
    for key in keys_to_clear:
        st.session_state.pop(key, None)
    st.rerun()


# =================================
# PROPOSAL DIALOG (shown as modal)
# =================================
# This dialog is rendered once at module level. It is triggered by
# setting st.session_state["open_proposal_for"] to a project index.
# Streamlit reruns the page, sees the flag, and calls st.dialog which
# opens the modal automatically.
#
# WHY use a dialog flag instead of rendering inline?
# A dialog gives the user a focused, distraction-free chat window
# without navigating away from the project list.

@st.dialog("Proposal Workshop", width="large")
def show_proposal_dialog(project_index: int, project: dict):
    """
    Render the proposal chat window inside a Streamlit dialog (modal).

    The dialog has two phases:
      Phase 1 -- If no proposal exists yet, generate one and show it.
      Phase 2 -- Once a proposal exists, show the full chat history
                 and a chat input so the user can refine it.
    """
    # Keys used to store this project''s chat history in session state.
    # Each project gets its own independent conversation thread.
    chat_key = f"proposal_chat_{project_index}"
    generating_key = f"proposal_generating_{project_index}"

    # Extract project data that we need for both the API call and display
    title = project.get("title", "Untitled Project")
    match_info = project.get("match", {})
    # Use the match explanation as the description; fall back to the project's
    # own description field if explanation is empty (some API responses omit it)
    description = (
        match_info.get("explanation", "")
        or project.get("description", "")
        or title  # last resort — at least give the LLM the title
    )
    budget = project.get("budget_or_rate", "")
    matching_skills = match_info.get("matching_skills", [])
    missing_skills = match_info.get("missing_skills", [])

    # Show project context at the top of the dialog so the user
    # knows which project the proposal is for
    st.markdown(f"**Project:** {title}")
    if budget:
        st.caption(f"Budget: {budget}")
    st.divider()

    # ── PHASE 1: Generate the initial proposal ──────────────────────
    # If there is no chat history yet, we have not generated the
    # proposal for this project. Do it now.
    if chat_key not in st.session_state:
        with st.spinner("Drafting your personalized proposal..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/api/career/freelance/proposal",
                    json={
                        "project_title": title,
                        "project_description": description,
                        "budget_or_rate": budget,
                        "matching_skills": matching_skills,
                        "missing_skills": missing_skills,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60,
                )

                if resp.status_code == 200:
                    proposal_text = resp.json().get("proposal", "")
                    # Store the proposal as the first "assistant" message
                    # in this project''s conversation history
                    st.session_state[chat_key] = [
                        {"role": "assistant", "content": proposal_text}
                    ]
                else:
                    st.error(f"Could not generate proposal (error {resp.status_code}). Please try again.")
                    return

            except requests.RequestException as e:
                st.error(f"Could not reach the API: {e}")
                return

    # ── PHASE 2: Display the chat history and accept refinements ────
    # At this point we always have at least one message (the proposal).
    chat_history = st.session_state.get(chat_key, [])

    # Render every message in the conversation so far.
    # "assistant" messages show the AI proposal / revision.
    # "user" messages show what the user asked for.
    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Copy-to-clipboard helper: show the latest proposal in a code
    # block so the user can copy it easily.
    # We find the last "assistant" message for the copy block.
    last_proposal = next(
        (m["content"] for m in reversed(chat_history) if m["role"] == "assistant"),
        None
    )

    if last_proposal:
        with st.expander("Copy proposal text"):
            st.code(last_proposal, language=None)

    # ── Chat input for refinements ───────────────────────────────────
    # The placeholder text guides the user on what kinds of things
    # they can ask for.
    user_input = st.chat_input(
        "Ask for changes... e.g. 'make it shorter', 'more confident tone', 'focus on Python'"
    )

    if user_input:
        # 1. Append the user's message to the history immediately
        #    so it appears in the chat window right away
        chat_history.append({"role": "user", "content": user_input})
        st.session_state[chat_key] = chat_history

        # 2. Call the chat endpoint with the full history.
        #    The backend sends all messages to the LLM so it has full
        #    context of every previous refinement request.
        with st.spinner("Revising your proposal..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/api/career/freelance/proposal/chat",
                    json={
                        "project_title": title,
                        "project_description": description,
                        # Send the full conversation history (stateless design --
                        # the backend does not store any session state, the
                        # frontend is the single source of truth for the history)
                        "messages": chat_history,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60,
                )

                if resp.status_code == 200:
                    reply = resp.json().get("reply", "")
                    # 3. Append the AI's reply, restore the dialog flag so
                    #    the dialog re-opens after rerun, then rerun.
                    chat_history.append({"role": "assistant", "content": reply})
                    st.session_state[chat_key] = chat_history
                    # Re-set the flag BEFORE rerun so Streamlit re-opens
                    # the dialog on the next render cycle.
                    st.session_state["open_proposal_for"] = project_index
                    st.rerun()
                else:
                    st.error(f"Could not get a reply (error {resp.status_code}). Please try again.")

            except requests.RequestException as e:
                st.error(f"Could not reach the API: {e}")


# =================================
# PROJECT CARDS -- 2-column grid
# =================================

if not projects and not analysis:
    st.info(
        "No freelance projects found. Try refreshing or make sure your "
        "profile has skills added."
    )

# Check if a proposal dialog should be opened for a specific project.
# This flag is set when the user clicks "View Proposal" on a card.
# We open the dialog BEFORE rendering the cards so Streamlit can
# display it as a modal overlay on top of the card grid.
#
# IMPORTANT: We do NOT pop the flag here. The dialog function itself
# re-sets the flag before calling st.rerun() when the user sends a
# chat message, so the dialog survives the rerun and stays open.
# The flag is only cleared when Streamlit naturally closes the dialog
# (i.e. the user clicks X or clicks outside), because in that case
# no rerun is triggered by our code, so the flag is never restored.
open_for = st.session_state.pop("open_proposal_for", None)
if open_for is not None and projects and open_for < len(projects):
    show_proposal_dialog(open_for, projects[open_for])

if projects:
    # Render in pairs (2-column grid)
    for row_start in range(0, len(projects), 2):
        row_projects = projects[row_start: row_start + 2]
        cols = st.columns(len(row_projects), gap="medium")

        for col_idx, (col, project) in enumerate(zip(cols, row_projects)):

            # Unique index for EVERY project across all rows.
            # This is used as the key for session state chat storage.
            project_index = row_start + col_idx

            with col:
                title = project.get("title", "Untitled Project")
                match_info = project.get("match", {})
                category = project.get("source", "")
                description = match_info.get("explanation", "")
                budget = project.get(
                    "budget",
                    project.get("budget_or_rate", "")
                )
                duration = project.get("duration", "")
                project_url = project.get(
                    "url",
                    project.get("job_url", "")
                )
                match_score = match_info.get("score", "")
                project_skills = match_info.get("matching_skills", [])

                # Skill names (capped at 4 badges for layout)
                if isinstance(project_skills, list):
                    project_skill_names = [
                        str(s) for s in project_skills if s
                    ][:4]
                else:
                    project_skill_names = []

                # Category display
                if isinstance(category, list):
                    category_str = ", ".join(str(c) for c in category[:2])
                else:
                    category_str = str(category) if category else ""

                # Whether a proposal has already been generated for this
                # project in this session (used to label the button)
                proposal_ready = f"proposal_chat_{project_index}" in st.session_state

                # ── PROJECT CARD ─────────────────────────────────────
                with st.container(
                    key=f"fl_card_{project_index}",
                    border=True
                ):

                    # Top row: icon + match badge
                    top_l, top_r = st.columns(
                        [3, 1],
                        vertical_alignment="center"
                    )

                    with top_l:
                        st.markdown(":material/arrow_outward:")

                    with top_r:
                        if match_score:
                            st.html(
                                f"""
                                <div class="cc-match-badge">
                                    {match_score}% match
                                </div>
                                """
                            )

                    # Title + source
                    st.html(
                        f"""
                        <div class="cc-profile-value"
                             style="font-size:17px; margin:4px 0 2px;">
                            {title}
                        </div>

                        <div class="cc-profile-detail"
                             style="margin:0 0 10px;">
                            {category_str}
                        </div>
                        """
                    )

                    # Short description (first 180 chars)
                    if description:
                        snippet = description[:180].strip()
                        if len(description) > 180:
                            snippet += "..."
                        st.write(snippet)

                    # Skill badges
                    if project_skill_names:
                        badges = "".join(
                            f'<span class="cc-skill-badge">{s}</span>'
                            for s in project_skill_names
                        )
                        st.html(
                            f"""
                            <div class="cc-skill-badges"
                                 style="margin:6px 0;">
                                {badges}
                            </div>
                            """
                        )

                    # Budget + Duration metadata row
                    meta_l, meta_r = st.columns(2)

                    with meta_l:
                        if budget:
                            st.html(
                                f"""
                                <div class="cc-meta-label">
                                    PROJECT BUDGET
                                </div>
                                <div class="cc-meta-value">
                                    {budget}
                                </div>
                                """
                            )

                    with meta_r:
                        if duration:
                            st.html(
                                f"""
                                <div class="cc-meta-label">
                                    DURATION
                                </div>
                                <div class="cc-meta-value">
                                    {duration}
                                </div>
                                """
                            )

                    # "Why it matches" section
                    match_explanation = match_info.get("explanation", "")
                    if not match_explanation:
                        matching = (
                            ", ".join(skills_list[:3])
                            if skills_list
                            else "your skills"
                        )
                        match_explanation = (
                            f"Your {matching} experience "
                            "match the main project requirements."
                        )

                    st.html(
                        f"""
                        <div class="cc-why-matches"
                             style="margin:10px 0;">

                            <div class="cc-why-title">
                                Why it matches you
                            </div>

                            <div class="cc-why-text">
                                {match_explanation}
                            </div>

                        </div>
                        """
                    )

                    # ── Action buttons ───────────────────────────────
                    btn_view, btn_proposal = st.columns(2)

                    # VIEW PROJECT button -- opens the URL on Freelancer.com
                    with btn_view:
                        if project_url:
                            with st.container(key=f"view_project_button_{project_index}"):

                              st.link_button(
                                "View project",
                                url=str(project_url),
                                type="primary",
                                use_container_width=True
                            )
                        else:
                            st.button(
                                "View project",
                                key=f"fl_view_{project_index}",
                                type="primary",
                                use_container_width=True,
                                disabled=True
                            )

                    # VIEW PROPOSAL button -- opens the proposal dialog.
                    # The label changes once a proposal has been generated
                    # so the user knows the proposal is ready to view.
                    with btn_proposal:
                        proposal_label = (
                            "View proposal"
                            if proposal_ready
                            else "Write proposal"
                        )

                        if st.button(
                            proposal_label,
                            key=f"fl_proposal_{project_index}",
                            use_container_width=True,
                        ):
                            # Set the flag that tells the dialog which
                            # project to open, then rerun so the dialog
                            # renders at the top of the page.
                            st.session_state["open_proposal_for"] = project_index
                            st.rerun()


# If no structured projects but analysis text exists, show raw text
if not projects and analysis:
    st.subheader("Agent Recommendations")
    st.markdown(analysis)
