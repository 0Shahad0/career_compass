from datetime import date
from html import escape
from pathlib import Path
import re
from components.navbar import render_navbar

import os
import requests
import streamlit as st


# =========================================================
# PAGE SETTINGS / API
# =========================================================

st.set_page_config(
    page_title="Certification Details | CareerCompass",
    page_icon=":material/workspace_premium:",
    layout="wide",
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"
API_BASE = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
)
LEVELS = ("Beginner", "Intermediate", "Advanced")

st.html(ASSETS / "home.css")


# =========================================================
# PAGE STYLE
# =========================================================

st.html(
    """
    <style>
    .cc-cert-title {
        color: #0B2E4F;
        font-size: 38px;
        font-weight: 700;
        line-height: 1.15;
        margin: 0 0 8px;
    }

    .cc-cert-meta {
        color: #627D98;
        font-size: 16px;
        margin-bottom: 14px;
    }

    .cc-cert-description {
        color: #627D98;
        font-size: 16px;
        line-height: 1.6;
        max-width: 720px;
        white-space: pre-wrap;
    }

    .cc-section-header {
        display: flex;
        gap: 15px;
        align-items: flex-start;
        margin-bottom: 22px;
    }

    .cc-section-number {
        min-width: 48px;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background: #E8F5FD;
        color: #1597E5;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        font-weight: 700;
    }

    .cc-section-title {
        color: #0B2E4F;
        font-size: 21px;
        font-weight: 700;
        margin: 0;
    }

    .cc-section-subtitle {
        color: #829AB1;
        font-size: 13px;
        margin-top: 3px;
    }

    .st-key-back_to_certifications button {
    width: 46px !important;
    height: 46px !important;
    min-width: 46px !important;
    min-height: 46px !important;

    padding: 0 !important;

    border: 1px solid #D9E2EC !important;
    border-radius: 9px !important;

    background: #FFFFFF !important;
    color: #1597E5 !important;

    box-shadow: none !important;
}

.st-key-back_to_certifications button:hover {
    background: #EDF7FD !important;
    border-color: #1597E5 !important;
}

.st-key-study_plan_setup .stFormSubmitButton button {
    background: #51BEE8 !important;
    border: 1px solid #51BEE8 !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

.st-key-study_plan_setup .stFormSubmitButton button:hover {
    background: #0B2E4F !important;
    border-color: #0B2E4F !important;
    color: #FFFFFF !important;
}

.st-key-study_plan_setup .stFormSubmitButton button:active {
    background: #0B2E4F !important;
    border-color: #0B2E4F !important;
    color: #FFFFFF !important;
}
    </style>
    """
)


# =========================================================
# HELPERS
# =========================================================

TARGET_ICON = """
<svg viewBox="0 0 24 24" width="28" height="28"
     fill="none" stroke="#1597E5" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="9"></circle>
    <circle cx="12" cy="12" r="5"></circle>
    <circle cx="12" cy="12" r="1"></circle>
    <path d="M15 9l6-6"></path>
    <path d="M17 3h4v4"></path>
</svg>
"""

CALENDAR_ICON = """
<svg viewBox="0 0 24 24" width="28" height="28"
     fill="none" stroke="#1597E5" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="5" width="18" height="16" rx="2"></rect>
    <path d="M16 3v4"></path>
    <path d="M8 3v4"></path>
    <path d="M3 10h18"></path>
</svg>
"""

GRADUATION_ICON = """
<svg viewBox="0 0 24 24" width="28" height="28"
     fill="none" stroke="#1597E5" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
    <path d="M2 9l10-5 10 5-10 5L2 9z"></path>
    <path d="M6 11.5V16c3.5 3 8.5 3 12 0v-4.5"></path>
    <path d="M22 9v6"></path>
</svg>
"""

def clear_plan():
    for key in (
        "cert_plan_response",
        "cert_plan_created",
        "cert_plan_request",
    ):
        st.session_state.pop(key, None)


def valid_exam_id(value):
    """Validate the ID's shape without changing the selected identifier."""
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(
            character.isspace() or ord(character) < 32
            for character in value
        )
    )


def text_value(value):
    return value.strip() if isinstance(value, str) else ""


def section_header(number, title, subtitle):
    st.html(
        f"""
        <div class="cc-section-header">
            <div class="cc-section-number">{escape(number)}</div>
            <div>
                <div class="cc-section-title">{escape(title)}</div>
                <div class="cc-section-subtitle">{escape(subtitle)}</div>
            </div>
        </div>
        """
    )


def plan_section_title(icon, title):
    st.html(
        f"""
        <div style="
            display:flex;
            align-items:center;
            gap:10px;
            margin-bottom:10px;
        ">
            <div style="display:flex; align-items:center;">
                {icon}
            </div>

            <div style="
                color:#0B2E4F;
                font-size:18px;
                font-weight:700;
            ">
                {escape(title)}
            </div>
        </div>
        """
    )

def authentication_error():
    st.error("Your session has expired. Please sign in again.")
    if st.button(
        "Sign in",
        type="primary",
        key="cert_details_sign_in_again",
    ):
        st.switch_page("pages/sign_in.py")
    st.stop()


def api_error_message(response):
    message = f"Could not generate the study plan ({response.status_code})."

    try:
        data = response.json()
    except ValueError:
        return message

    if not isinstance(data, dict):
        return message

    detail = data.get("detail")

    if isinstance(detail, str) and detail.strip():
        return f"{message} {detail.strip()}"

    if isinstance(detail, list):
        errors = []

        for item in detail:
            if not isinstance(item, dict):
                continue

            error_text = text_value(item.get("msg"))
            if not error_text:
                continue

            location = item.get("loc")
            field = ""

            if isinstance(location, (list, tuple)):
                field = ".".join(
                    str(part)
                    for part in location
                    if part not in ("body", "query", "path")
                )

            errors.append(
                f"{field}: {error_text}" if field else error_text
            )

        if errors:
            return message + "\n\n" + "\n\n".join(errors)

    return message


def parse_study_plan(markdown):
    """Split only the expected headings; otherwise preserve the full response."""
    expected = [
        (2, "exam information", "information"),
        (3, "domains and weights", "domains"),
        (2, "personalized study plan", "introduction"),
        (3, "study priorities", "priorities"),
        (3, "weekly plan", "weekly"),
        (3, "exam preparation", "preparation"),
        (2, "practice & official resources", "resources"),
    ]

    sections = {key: [] for _, _, key in expected}
    position = 0
    current = None
    fence = None

    for line in markdown.splitlines():
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)

        if fence is not None:
            if current is None:
                return None

            sections[current].append(line)

            if (
                fence_match
                and fence_match.group(1)[0] == fence[0]
                and len(fence_match.group(1)) >= len(fence)
                and not fence_match.group(2).strip()
            ):
                fence = None

            continue

        if fence_match:
            if current is None:
                return None

            fence = fence_match.group(1)
            sections[current].append(line)
            continue

        heading = re.match(r"^ {0,3}(#{2,3})[ \t]+(.+?)\s*$", line)

        if heading:
            title = re.sub(
                r"[ \t]+#+[ \t]*$",
                "",
                heading.group(2),
            )

            if position >= len(expected):
                return None

            level, label, key = expected[position]

            if (
                len(heading.group(1)) != level
                or title.casefold() != label
            ):
                return None

            current = key
            position += 1
            continue

        if current is None:
            if line.strip():
                return None
        else:
            sections[current].append(line)

    if fence is not None or position != len(expected):
        return None

    result = {
        key: "\n".join(lines).strip()
        for key, lines in sections.items()
    }

    if any(
        not result[key]
        for key in (
            "information",
            "domains",
            "priorities",
            "weekly",
            "preparation",
            "resources",
        )
    ):
        return None

    return result


# =========================================================
# AUTHENTICATION
# =========================================================

token = st.session_state.get("token")

if not token:
    clear_plan()
    st.session_state.pop("cert_plan_owner", None)
    st.session_state.pop("cert_plan_auth_error", None)

    st.warning("Please sign in to view certification details.")

    if st.button("Sign in", type="primary"):
        st.switch_page("pages/sign_in.py")

    st.stop()


# =========================================================
# NAVIGATION
# =========================================================

render_navbar("Certifications")

if st.button(
    "",
    key="back_to_certifications",
    type="tertiary",
    icon=":material/arrow_back:",
):
    st.switch_page("pages/certifications.py")


# =========================================================
# SELECTED CERTIFICATION / SESSION OWNERSHIP
# =========================================================

selected = st.session_state.get("selected_certification")

if not isinstance(selected, dict) or not selected:
    clear_plan()
    st.session_state.pop("cert_plan_owner", None)
    st.warning("No certification was selected. Go back to Certifications.")
    st.stop()

exam_id = selected.get("exam_id")

if not valid_exam_id(exam_id):
    clear_plan()
    st.session_state.pop("cert_plan_owner", None)
    st.error(
        "This selection has no valid Cert Atlas exam ID. "
        "Go back to Certifications and select the certification again."
    )
    st.stop()

# Never reuse a response belonging to another exam or signed-in session.
owner = (token, exam_id)

if st.session_state.get("cert_plan_owner") != owner:
    clear_plan()

    for key in (
        "cert_current_level",
        "cert_exam_date",
        "cert_plan_auth_error",
    ):
        st.session_state.pop(key, None)

    st.session_state["cert_plan_owner"] = owner

if st.session_state.get("cert_plan_auth_error"):
    authentication_error()

exam_name = (
    text_value(selected.get("name"))
    or text_value(selected.get("exam_name"))
    or text_value(selected.get("certification_name"))
    or "Certification"
)

exam_code = text_value(selected.get("exam_code"))

provider = (
    text_value(selected.get("provider"))
    or text_value(selected.get("certifying_body"))
)

match = selected.get("match")
description = (
    text_value(match.get("explanation"))
    if isinstance(match, dict)
    else ""
)

# Validate restored widget state before creating the widgets.
if st.session_state.get("cert_current_level", LEVELS[0]) not in LEVELS:
    st.session_state.pop("cert_current_level", None)

saved_date = st.session_state.get("cert_exam_date")
if saved_date is not None and type(saved_date) is not date:
    st.session_state.pop("cert_exam_date", None)


# =========================================================
# CERTIFICATION HEADER + PLAN FORM
# =========================================================

hero_left, hero_right = st.columns(
    [1.45, 1],
    gap="large",
    vertical_alignment="center",
)

with hero_left:
    st.html(
        f'<h1 class="cc-cert-title">{escape(exam_name)}</h1>'
    )

    metadata = [
        escape(value)
        for value in (exam_code, provider)
        if value
    ]

    if metadata:
        st.html(
            '<div class="cc-cert-meta">'
            + " &nbsp; • &nbsp; ".join(metadata)
            + "</div>"
        )

    if description:
        st.html(
            '<div class="cc-cert-description">'
            + escape(description)
            + "</div>"
        )

with hero_right:
    with st.container(border=True, key="study_plan_setup"):
        st.markdown("### Prepare your study plan")
        st.caption(
            "Set your current level and target exam date "
            "to generate a personalized plan."
        )

        with st.form("cert_study_plan_form"):
            level_col, date_col = st.columns(2, gap="medium")

            with level_col:
                current_level = st.selectbox(
                    "Current level",
                    LEVELS,
                    key="cert_current_level",
                )

            with date_col:
                exam_date = st.date_input(
                    "Exam date",
                    value=None,
                    key="cert_exam_date",
                )

            create_plan = st.form_submit_button(
                "Create Study Plan",
                type="primary",
                use_container_width=True,
            )


# =========================================================
# CREATE STUDY PLAN
# =========================================================

if create_plan:
    clear_plan()

    if current_level not in LEVELS:
        st.error("Choose Beginner, Intermediate, or Advanced.")

    elif type(exam_date) is not date:
        st.warning("Please select an exam date.")

    elif exam_date < date.today():
        st.error("Exam date cannot be in the past.")

    else:
        payload = {
            "selected_certification": exam_id,
            "current_level": current_level,
            "exam_date": exam_date.isoformat(),
        }

        with st.spinner("Creating your personalized study plan..."):
            try:
                response = requests.post(
                    f"{API_BASE}/api/career/certifications/study-plan",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=(10, 180),
                )

            except requests.Timeout:
                st.error(
                    "The request timed out. Please try creating "
                    "your study plan again."
                )

            except requests.ConnectionError:
                st.error(
                    "Could not connect to the API. "
                    "Please check that the backend is running and try again."
                )

            except requests.RequestException:
                st.error(
                    "The study plan request failed. Please try again."
                )

            else:
                if response.status_code == 401:
                    st.session_state["cert_plan_auth_error"] = True
                    st.rerun()

                elif response.status_code != 200:
                    st.error(api_error_message(response))

                else:
                    try:
                        data = response.json()
                    except ValueError:
                        st.error(
                            "The backend returned invalid JSON. "
                            "Please try again."
                        )
                    else:
                        study_plan = (
                            data.get("study_plan")
                            if isinstance(data, dict)
                            else None
                        )

                        if (
                            not isinstance(study_plan, str)
                            or not study_plan.strip()
                        ):
                            st.error(
                                "The backend response did not contain "
                                "a non-empty study_plan. Please try again."
                            )

                        else:
                            # Store the actual response without rewriting it.
                            st.session_state["cert_plan_response"] = data
                            st.session_state["cert_plan_request"] = (
                                payload.copy()
                            )
                            st.session_state["cert_plan_created"] = (
                                parse_study_plan(study_plan) is not None
                            )


# =========================================================
# DISPLAY THE ACTUAL BACKEND RESULT
# =========================================================

st.write("")

plan_response = st.session_state.get("cert_plan_response")
plan_request = st.session_state.get("cert_plan_request")

if plan_response is None:
    st.info(
        "Choose your current level and exam date to load exam "
        "information and create your study plan."
    )
    st.stop()

# A cached response is usable only with its recorded exact exam ID.
if (
    st.session_state.get("cert_plan_owner") != owner
    or not isinstance(plan_request, dict)
    or plan_request.get("selected_certification") != exam_id
):
    clear_plan()
    st.info(
        "Choose your current level and exam date to load exam "
        "information and create your study plan."
    )
    st.stop()

study_plan = (
    plan_response.get("study_plan")
    if isinstance(plan_response, dict)
    else None
)

if not isinstance(study_plan, str) or not study_plan.strip():
    clear_plan()
    st.error(
        "The saved backend response is invalid. "
        "Please create your study plan again."
    )
    st.stop()

sections = parse_study_plan(study_plan)

if sections is None:
    st.session_state["cert_plan_created"] = False

    # Stage 2 can return a validation/error message with HTTP 200.
    # Unexpected Markdown is also shown intact rather than losing content.
    st.warning(
        "The backend did not return the expected complete study-plan "
        "sections. Its response is shown below."
    )

    with st.container(border=True):
        st.markdown(study_plan, unsafe_allow_html=False)

    st.stop()

st.session_state["cert_plan_created"] = True

st.caption(
    f"Plan generated for {plan_request.get('current_level')} level "
    f"and exam date {plan_request.get('exam_date')}. "
    "Submit the form again to apply changes."
)

with st.container(border=True, key="exam_information_card"):
    section_header(
        "01",
        "Exam Information",
        "Exam details returned for the selected certification.",
    )

    info_col, domain_col = st.columns(
        [1, 1.15],
        gap="large",
    )

    with info_col:
        st.markdown(
            sections["information"],
            unsafe_allow_html=False,
        )

    with domain_col:
        st.markdown("### Domains and weights")
        st.markdown(
            sections["domains"],
            unsafe_allow_html=False,
        )

st.write("")

with st.container(border=True, key="personalized_plan_card"):
    section_header(
        "02",
        "Personalized Study Plan",
        "Your preparation plan based on the submitted level and exam date.",
    )

    if sections["introduction"]:
        st.markdown(
            sections["introduction"],
            unsafe_allow_html=False,
        )

    with st.container(border=True):
        plan_section_title(TARGET_ICON,"Study Priorities",)
        st.markdown(
            sections["priorities"],
            unsafe_allow_html=False,
        )

    with st.container(border=True):
        plan_section_title(CALENDAR_ICON, "Weekly Plan",)
        st.markdown(
            sections["weekly"],
            unsafe_allow_html=False,
        )

    with st.container(border=True):
        plan_section_title( GRADUATION_ICON,"Exam Preparation",)
        st.markdown(
            sections["preparation"],
            unsafe_allow_html=False,
        )
        
    st.write("")

    with st.container(
       border=True,
       key="practice_official_resources_card",
):
        section_header(
          "03",
          "Practice & Official Resources",
          "Use these official resources to prepare for your exam.",
    )

        st.markdown(
           sections["resources"],
           unsafe_allow_html=False,
    )