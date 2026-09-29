from html import escape
from pathlib import Path
from components.navbar import render_navbar

import os
import requests
import streamlit as st

st.set_page_config(
    page_title="Certifications | CareerCompass",
    page_icon=":material/workspace_premium:",
    layout="wide",
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"
API_BASE = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
)
PAGE_SIZE = 10

st.html(ASSETS / "home.css")
st.html("""
<style>
.cert-name {
    color: #0B2E4F;
    font-size: 20px;
    font-weight: 700;
}
.cert-meta {
    color: #627D98;
    font-size: 14px;
    margin: 6px 0 12px;
}
.cert-pill {
    display: inline-block;
    background: #E6F7F2;
    color: #16705A;
    padding: 4px 9px;
    border-radius: 8px;
    margin: 3px;
    font-size: 12px;
}
    .score-label {
    color: #627D98;
    font-size: 12px;
    margin-bottom: 2px;
}

.score-value {
    color: #1597E5;
    font-size: 24px;
    font-weight: 600;
    line-height: 1.1;
}

.score-note {
    color: #829AB1;
    font-size: 11px;
    line-height: 1.35;
    margin-top: 5px;
}

/* Change selected radio from red to light blue */
div[role="radiogroup"] label[data-baseweb="radio"]
input[type="radio"]:checked + div {
    background-color: #39C6F4 !important;
    border-color: #39C6F4 !important;
}

/* White dot inside selected radio */
div[role="radiogroup"] label[data-baseweb="radio"]
input[type="radio"]:checked + div > div {
    background-color: white !important;
}

/* Search button */
.st-key-cert_catalog_search .stFormSubmitButton button {
    background: #1597E5 !important;
    border: 1px solid #1597E5 !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}

/* Hover */
.st-key-cert_catalog_search .stFormSubmitButton button:hover {
    background: #0B2E4F !important;
    border-color: #0B2E4F !important;
    color: #FFFFFF !important;
}

/* While pressing */
.st-key-cert_catalog_search .stFormSubmitButton button:active {
    background: #0B2E4F !important;
    border-color: #0B2E4F !important;
    color: #FFFFFF !important;
}

/* After clicking / focus */
.st-key-cert_catalog_search .stFormSubmitButton button:focus {
    background: #0B2E4F !important;
    border-color: #0B2E4F !important;
    color: #FFFFFF !important;
    box-shadow: none !important;
}
</style>
""")

token = st.session_state.get("token")

if not token:
    st.warning("Please sign in to view certifications.")
    if st.button("Sign in", type="primary"):
        st.switch_page("pages/sign_in.py")
    st.stop()

# =================================
# NAVBAR
# =================================

render_navbar("Certifications")

# Prevent cached results from a previous signed-in session being reused.
if st.session_state.get("cert_stage1_owner") != token:
    st.session_state["cert_stage1_owner"] = token
    st.session_state["cert_stage1_pages"] = {}
    st.session_state["cert_stage1_offset"] = 0
    st.session_state["cert_stage1_query"] = ""
    st.session_state["cert_stage1_search_offset"] = 0
    st.session_state["cert_stage1_search_pages"] = {}



st.title("Certifications")
st.caption(
    "Explore recommendations based on your education, experience, "
    "and skills, or search the full catalog."
)


def request_page(path, params, method="GET"):
    try:
        response = requests.request(
            method,
            f"{API_BASE}/api/career/{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Invalid response")

        return data

    except requests.Timeout:
        st.error("The request timed out. Please retry.")

    except (requests.RequestException, ValueError):
        st.error(
            "Could not load certifications. Please retry or sign in again."
        )

    return None


def select_certification(item):
    if (
        not isinstance(item.get("exam_id"), str)
        or not item["exam_id"].strip()
    ):
        st.error("This result has no valid Cert Atlas exam ID.")
        return

    st.session_state["selected_certification"] = dict(item)

    # Both paths enter the same details page with the exact exam_id.
    for key in (
        "cert_plan_response",
        "cert_plan_created",
        "cert_exam_date",
        "cert_current_level",
    ):
        st.session_state.pop(key, None)

    st.switch_page("pages/certification_details.py")


def render_result(item, position, manual=False):
    exam_id = item.get("exam_id")

    with st.container(border=True):
        left, right = st.columns([5, 1.4])

        with left:
            st.html(
                f'<div class="cert-name">'
                f'{escape(str(item.get("name", "Certification")))}'
                f'</div>'
                f'<div class="cert-meta">'
                f'{escape(str(item.get("provider") or "Not available"))}'
                f' · '
                f'{escape(str(item.get("exam_code") or "Exam code unavailable"))}'
                f'</div>'
            )

            if manual:
                status = item.get("lifecycle_status")
                if status:
                    st.caption(f"Catalog status: {status}")

            else:
                match = item.get("match") or {}
                st.write(
                    match.get("explanation") or "Explanation unavailable."
                )
                st.caption("Matching skills")

                skills = match.get("matching_skills") or []
                if skills:
                    st.html("".join(
                        f'<span class="cert-pill">'
                        f'{escape(str(skill))}'
                        f'</span>'
                        for skill in skills
                    ))



        with right:
            if not manual:
                score = (item.get("match") or {}).get("score")

                if isinstance(score, (int, float)):
                     st.html(
                         f"""
                        <div class="score-label">Profile Recommendation Score</div>
                        <div class="score-value">{int(score)}</div>
                        <div class="score-note">
                        Based on your education, experience, and skills.
                      </div>
                      """
                )
                else:
                    st.caption("Recommendation score unavailable.")

            if st.button(
                "View certification",
                key=(
                    f"cert_select_"
                    f"{'search' if manual else 'rec'}_"
                  f"{position}_{exam_id}"
                ),
                type="primary",
                disabled=not bool(exam_id),
            ):
                select_certification(item)


def render_pagination(pagination, state_key, prefix):
    offset = int(
        pagination.get(
            "offset",
            st.session_state.get(state_key, 0),
        )
    )
    total = int(pagination.get("total", 0))
    returned = int(pagination.get("returned", 0))

    left, center, right = st.columns([1, 3, 1])

    with left:
        if st.button(
            "Previous",
            key=f"{prefix}_previous",
            disabled=offset <= 0,
        ):
            st.session_state[state_key] = max(0, offset - PAGE_SIZE)
            st.rerun()

    with center:
        if returned:
            st.caption(f"{offset + 1}–{offset + returned} of {total}")
        else:
            st.caption(f"0 shown · {total} results")

    with right:
        next_offset = pagination.get("next_offset")
        if st.button(
            "Next",
            key=f"{prefix}_next",
            disabled=(
                not pagination.get("has_more")
                or next_offset is None
            ),
        ):
            st.session_state[state_key] = int(next_offset)
            st.rerun()


mode = st.radio(
    "Explore certifications",
    [
        "Recommended Certifications",
        "Search Any Certification",
    ],
    horizontal=True,
)

if mode == "Recommended Certifications":
    if st.button("Refresh recommendations", type="secondary"):
        st.session_state["cert_stage1_pages"] = {}
        st.session_state["cert_stage1_offset"] = 0

    offset = st.session_state["cert_stage1_offset"]
    pages = st.session_state["cert_stage1_pages"]

    if offset not in pages:
        with st.spinner("Finding relevant certifications..."):
            data = request_page(
                "certifications",
                {"offset": offset, "limit": PAGE_SIZE},
                "POST",
            )
        if data is not None:
            pages[offset] = data

    data = pages.get(offset)

    if data is not None:
        if data.get("analysis"):
            st.caption(data["analysis"])

        items = data.get("recommendations") or []
        if not items:
            st.info(
                "No recommendations to show. "
                "Manual catalog search remains available."
            )

        for index, item in enumerate(items, offset):
            render_result(item, index)

        render_pagination(
            data.get("pagination") or {},
            "cert_stage1_offset",
            "recommendations",
        )

    elif st.button("Retry recommendations"):
        st.rerun()

else:
    st.caption(
        "Search by certification name, exam code, or provider. "
        "Your profile does not filter these results."
    )

    with st.form("cert_catalog_search"):
        query = st.text_input(
            "Certification search",
            max_chars=200,
            placeholder=(
                "PL-300, AWS Solutions Architect, Salesforce Administrator"
            ),
        )
        submitted = st.form_submit_button(
            "Search",
            type="primary",
        )

    if submitted:
        st.session_state["cert_stage1_query"] = query.strip()
        st.session_state["cert_stage1_search_offset"] = 0
        st.session_state["cert_stage1_search_pages"] = {}

        if not query.strip():
            st.warning(
                "Enter a certification name, exam code, or provider."
            )

    active_query = st.session_state["cert_stage1_query"]

    if active_query:
        offset = st.session_state["cert_stage1_search_offset"]
        pages = st.session_state["cert_stage1_search_pages"]
        key = (active_query, offset)

        if key not in pages:
            with st.spinner("Searching Cert Atlas..."):
                data = request_page(
                    "certifications/search",
                    {
                        "query": active_query,
                        "offset": offset,
                        "limit": PAGE_SIZE,
                    },
                )

            if data is not None:
                pages[key] = data

        data = pages.get(key)

        if data is not None:
            items = data.get("certifications") or []

            if not items:
                st.info("No certifications found for this search.")

            for index, item in enumerate(items, offset):
                render_result(item, index, manual=True)

            render_pagination(
                data.get("pagination") or {},
                "cert_stage1_search_offset",
                "catalog",
            )

        elif st.button("Retry search"):
            st.rerun()