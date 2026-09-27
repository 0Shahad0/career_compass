from pathlib import Path

import streamlit as st


# ---------------------------------
# Assets
# ---------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "assets"
logo = ASSETS / "logo.png"


# ---------------------------------
# User info
# ---------------------------------

def _get_user_info():
    profile = st.session_state.get("profile") or {}
    user_email = st.session_state.get("user_email", "")

    personal = profile.get("personal_information", {})

    display_name = (
        personal.get("name")
        or user_email.split("@")[0].title()
        or "User"
    )

    initials = "".join(
        part[0].upper()
        for part in display_name.split()
        if part
    )[:2] or "U"

    return display_name, user_email, initials


# ---------------------------------
# User menu
# ---------------------------------

@st.dialog("CAREERCOMPASS", width="medium")
def user_menu():

    display_name, user_email, _ = _get_user_info()

    st.html(
        f"""
        <div class="user-menu-info">
            <h2>{display_name}</h2>
            <p>{user_email}</p>
        </div>
        """
    )

    profile_col, signout_col = st.columns(
        [1, 1],
        gap="small"
    )

    with profile_col:
        if st.button(
            "View profile",
            key="dialog_view_profile",
            use_container_width=True
        ):
            st.switch_page("pages/profile_review.py")

    with signout_col:
        if st.button(
            "Sign out",
            key="dialog_signout",
            type="primary",
            use_container_width=True
        ):
            for key in [
                "token",
                "user_email",
                "user_id",
                "profile",
                "portfolio_profile",
                "cv_uploaded",
                "cv_name",
            ]:
                st.session_state.pop(key, None)

            st.switch_page("app.py")


# ---------------------------------
# Navbar
# ---------------------------------

def render_navbar(active_page: str):
    st.html(ASSETS / "navbar.css")

    _, _, initials = _get_user_info()

    # Active page only
    active_key = {
        "Dashboard": "nav_dashboard",
        "Jobs": "nav_jobs",
        "Freelance": "nav_freelance",
        "Certifications": "nav_certifications",
    }.get(active_page)

    # Change active underline/color depending on page
    if active_key:
        st.html(
            f"""
            <style>
                .st-key-dash_nav_links button {{
                    color: #627D98 !important;
                    font-weight: 400 !important;
                    border-bottom: 3px solid transparent !important;
                }}

                .st-key-{active_key} button {{
                    color: #1597E5 !important;
                    font-weight: 600 !important;
                    border-bottom: 3px solid #1597E5 !important;
                }}
            </style>
            """
        )

    # Same navbar structure as Dashboard
    with st.container(key="dash_nav"):

        logo_col, nav_col, user_col = st.columns(
            [1, 3, 1],
            vertical_alignment="center"
        )

        # Logo — far left
        with logo_col:
            st.image(
                logo,
                width=145
            )

        # Navigation — centered
        with nav_col:
            with st.container(
                key="dash_nav_links",
                horizontal=True,
                horizontal_alignment="center",
                vertical_alignment="center",
            ):

                if st.button(
                    "Dashboard",
                    key="nav_dashboard",
                    type="tertiary",
                ):
                    st.switch_page("pages/dashboard.py")

                if st.button(
                    "Jobs",
                    key="nav_jobs",
                    type="tertiary",
                ):
                    st.switch_page("pages/jobs.py")

                if st.button(
                    "Freelance",
                    key="nav_freelance",
                    type="tertiary",
                ):
                    st.switch_page("pages/freelance.py")

                if st.button(
                    "Certifications",
                    key="nav_certifications",
                    type="tertiary",
                ):
                    st.switch_page("pages/certifications.py")

        # User — far right
        with user_col:
            if st.button(
                initials,
                key="user_avatar_btn"
            ):
                user_menu()