import os
import streamlit as st
from pathlib import Path
import requests
from components.navbar import render_navbar


from components.profile import render_profile_editor


st.set_page_config(
    page_title="Profile Review | CareerCompass",
    page_icon="🧭",
    layout="wide",
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"
st.html(ASSETS / "home.css")

API_BASE = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
)

# --------------------------------------------------
# Load profile
# --------------------------------------------------

profile_data = st.session_state.get("profile")

# Temporary fallback:
# until CV + Portfolio are merged, use the portfolio extraction.
if profile_data is None:
    profile_data = st.session_state.get("portfolio_profile")


if profile_data is None:
    st.warning("No extracted profile is available yet.")
    st.info("Please upload your CV or add your portfolio first.")
    st.stop()

# --------------------------------------------------
# Navbar
# --------------------------------------------------

render_navbar("Profile")
# --------------------------------------------------
# Header
# --------------------------------------------------

left, center, right = st.columns([1, 1.5, 1])

with center:
       st.title("Review Your Profile")
       st.write(
        "We've extracted the following information from your documents "
        "and portfolio. Please review and edit it before continuing."
    )


# --------------------------------------------------
# Extraction warnings
# --------------------------------------------------

warnings = st.session_state.get("portfolio_warnings", [])

if warnings:
    with st.expander("Extraction notes"):
        for warning in warnings:
            st.write(f"• {warning}")


# --------------------------------------------------
# Profile editor
# --------------------------------------------------

with center:
    updated_profile = render_profile_editor(profile_data)


# --------------------------------------------------
# When the user clicks "Save & Continue", persist to
# the backend and redirect to the dashboard.
# --------------------------------------------------

if updated_profile:
    # Save into session state
    profile_dict = updated_profile.model_dump(mode="json")
    st.session_state["profile"] = profile_dict

    # If we have a token, persist to the backend
    token = st.session_state.get("token")

    if token:
        try:
            with st.spinner("Saving your profile..."):
                response = requests.post(
                    f"{API_BASE}/api/auth/profile",
                    json=profile_dict,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=20,
                )

            if response.status_code == 200:
                st.switch_page("pages/dashboard.py")
            else:
                st.error(
                    f"Could not save profile to server "
                    f"(status {response.status_code}). "
                    "You can still continue to the dashboard."
                )
                if st.button("Continue to Dashboard anyway"):
                    st.switch_page("pages/dashboard.py")

        except requests.RequestException as e:
            st.error(
                f"Could not reach the CareerCompass API: {e}. "
                "Your profile is saved locally — you can still continue."
            )
            if st.button("Continue to Dashboard anyway"):
                st.switch_page("pages/dashboard.py")

    else:
        # No token (guest flow) — go straight to dashboard
        st.switch_page("pages/dashboard.py")