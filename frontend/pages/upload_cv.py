from pathlib import Path
import os
import streamlit as st


# -----------------------------
# Page settings
# -----------------------------

import requests
import streamlit as st

from components.portfolio import portfolio_section


# --------------------------------------------------
# Page settings
# --------------------------------------------------

st.set_page_config(
    page_title="Upload CV | CareerCompass",
    page_icon="🧭",
    layout="wide",
)


# --------------------------------------------------
# Assets
# --------------------------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "assets"

st.html(ASSETS / "home.css")

API_BASE = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
)


# --------------------------------------------------
# Page layout
# --------------------------------------------------

left, center, right = st.columns(
    [1, 1.4, 1]
)


with center:

    st.image(
        ASSETS / "logo.png",
        width=180,
    )

    st.title("Upload your CV")

    st.write(
        "Upload your CV so CareerCompass can "
        "extract your profile information automatically."
    )


    # --------------------------------------------------
    # CV Upload
    # --------------------------------------------------

    cv_file = st.file_uploader(
        "Choose your CV",
        type=["pdf"],
    )


    if cv_file is not None:

        # File is selected, but not uploaded yet
        st.success(
            f"{cv_file.name} selected successfully."
        )

        st.session_state["cv_name"] = cv_file.name


        # --------------------------------------------------
        # Get authentication token
        # --------------------------------------------------

        token = st.session_state.get("token")

        # --------------------------------------------------
        # Portfolio
        # Optional extra source
        # --------------------------------------------------

        st.divider()

        portfolio_url = portfolio_section()

        # --------------------------------------------------
        # Extract CV + Portfolio
        # --------------------------------------------------

        if st.button(
            "Extract Profile",
            type="primary",
            use_container_width=True,
        ):

            # User must be logged in
            if not token:

                st.error(
                    "Your session has expired. "
                    "Please log in again."
                )

                st.stop()


            # Prepare CV file
            files = {
                "file": (
                    cv_file.name,
                    cv_file.getvalue(),
                    "application/pdf",
                )
            }


            # Prepare portfolio URL
            data = {}

            if portfolio_url:
                data["portfolio_url"] = portfolio_url


            try:

                with st.spinner(
                    "Extracting your CV and portfolio..."
                ):

                    response = requests.post(
                        f"{API_BASE}/api/users/me/profile/extract",
                        files=files,
                        data=data,
                        headers={
                            "Authorization": f"Bearer {token}"
                        },
                        timeout=120,
                    )


                # --------------------------------------------------
                # Extraction successful
                # --------------------------------------------------

                if response.status_code == 200:

                    result = response.json()

                    # Save the combined profile
                    st.session_state["profile"] = result["profile"]

                    # Save portfolio warnings
                    st.session_state["portfolio_warnings"] = (
                        result.get(
                            "portfolio_warnings",
                            [],
                        )
                    )

                    st.session_state["cv_uploaded"] = True

                    st.success(
                        "CV and portfolio extracted successfully."
                    )

                    # Go to Profile Review
                    st.switch_page(
                        "pages/profile_review.py"
                    )


                # --------------------------------------------------
                # Backend error
                # --------------------------------------------------

                else:

                    st.error(
                        "Profile extraction failed. "
                        f"Status: {response.status_code}"
                    )

                    st.code(
                        response.text
                    )


            except requests.Timeout:

                st.error(
                    "Profile extraction is taking too long. "
                    "Please try again."
                )


            except requests.RequestException as e:

                st.error(
                    "Could not connect to the "
                    f"CareerCompass API: {e}"
                )