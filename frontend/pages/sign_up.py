from pathlib import Path
import os

import requests
import streamlit as st


# ---------------------------------
# Page settings
# ---------------------------------

st.set_page_config(
    page_title="Create Account | CareerCompass",
    page_icon="🧭",
    layout="wide",
)


# ---------------------------------
# Assets
# ---------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "assets"

st.html(ASSETS / "sign-up.css")

API_BASE = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
)

# =================================
# SIGN UP PAGE
# =================================

with st.container(key="signup_shell"):

    left, right = st.columns(
        [1, 1],
        gap=None,
        vertical_alignment="center",
    )


    # =================================
    # LEFT SIDE
    # =================================

    with left:

        with st.container(key="signup_left"):

            st.html(
                """
                <div class="signup-left-content">

                    <p class="signup-eyebrow">
                        A CAREER THAT FITS YOU
                    </p>

                    <h1 class="signup-main-title">
                        Good opportunities<br>
                        start with your story.
                    </h1>

                    <p class="signup-description">
                        Bring your experience.
                        Discover where it can take you next.
                    </p>

                </div>
                """
            )


    # =================================
    # RIGHT SIDE
    # =================================

    with right:

        with st.container(key="signup_right"):

            # Back to home
            if st.button(
                "",
                icon=":material/arrow_back:",
                key="back_home_signup",
                type="tertiary",
            ):
                st.switch_page("app.py")


            st.html(
                """
                <div class="signup-form-heading">

                    <p class="signup-eyebrow">
                        WELCOME TO CAREERCOMPASS
                    </p>

                    <h2>
                        Start your next chapter.
                    </h2>

                    <p>
                        Create an account to find your direction.
                    </p>

                </div>
                """
            )


            # ---------------------------------
            # Form
            # ---------------------------------

            full_name = st.text_input(
                "Full name",
                placeholder="Alex Morgan",
            )

            email = st.text_input(
                "Email address",
                placeholder="you@example.com",
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="At least 8 characters",
            )

            confirm_password = st.text_input(
                "Confirm password",
                type="password",
            )


            # ---------------------------------
            # Create account
            # ---------------------------------

            if st.button(
                "Create account",
                type="primary",
                use_container_width=True,
                key="signup_create_account",
            ):

                if (
                    not full_name
                    or not email
                    or not password
                    or not confirm_password
                ):
                    st.warning(
                        "Please complete all fields."
                    )

                elif password != confirm_password:
                    st.error(
                        "Passwords do not match."
                    )

                elif len(password) < 8:
                    st.error(
                        "Password must be at least 8 characters."
                    )

                else:
                    try:

                        with st.spinner(
                            "Creating your account..."
                        ):

                            response = requests.post(
                                f"{API_BASE}/api/auth/register",
                                json={
                                    "email": email,
                                    "password": password,
                                },
                                timeout=15,
                            )


                        if response.status_code == 201:

                            data = response.json()

                            st.session_state["token"] = (
                                data["access_token"]
                            )

                            st.session_state["user_email"] = email

                            # Keep the name locally for now.
                            # Do not send it to the API unless
                            # the backend register schema supports it.
                            st.session_state["full_name"] = full_name

                            st.switch_page(
                                "pages/upload_cv.py"
                            )


                        elif response.status_code == 400:

                            detail = (
                                response
                                .json()
                                .get("detail", "")
                            )

                            if "already registered" in detail:

                                st.error(
                                    "An account with this email "
                                    "already exists. "
                                    "Please sign in instead."
                                )

                            else:

                                st.error(
                                    f"Registration failed: {detail}"
                                )


                        elif response.status_code == 422:

                            st.error(
                                "Please enter a valid email address."
                            )


                        else:

                            st.error(
                                "Registration failed "
                                f"(status {response.status_code}). "
                                "Please try again."
                            )


                    except requests.Timeout:

                        st.error(
                            "The server is taking too long "
                            "to respond. Please try again."
                        )


                    except requests.RequestException as e:

                        st.error(
                            "Could not connect to "
                            f"CareerCompass API: {e}"
                        )


            # ---------------------------------
            # Sign in
            # ---------------------------------

            with st.container(
                key="signup_signin_row",
                horizontal=True,
                horizontal_alignment="center",
                vertical_alignment="center",
            ):

                st.html(
                    """
                      <span class="signup-login-text">
                      Already have an account?
                     </span>
                   """
                  )

                if st.button(
                    "Sign in",
                    type="tertiary",
                    key="signup_signin",
                ):
                    st.switch_page(
                        "pages/sign_in.py"
                    )