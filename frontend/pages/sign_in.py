from pathlib import Path

import requests
import streamlit as st


# ---------------------------------
# Page settings
# ---------------------------------

st.set_page_config(
    page_title="Sign In | CareerCompass",
    page_icon="🧭",
    layout="wide",
)


# ---------------------------------
# Assets
# ---------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "assets"

st.html(ASSETS / "home.css")
st.html(ASSETS / "sign_in.css")

API_BASE = "http://127.0.0.1:8000"


# =================================
# SIGN IN PAGE
# =================================

with st.container(key="signin_shell"):

    left, right = st.columns(
        [1, 1],
        gap=None,
        vertical_alignment="center",
    )


    # =================================
    # LEFT SIDE
    # =================================

    with left:

        with st.container(key="signin_left"):

            st.html(
                """
                <div class="signin-left-content">

                    <p class="signin-eyebrow">
                        YOUR CAREER, CONTINUED
                    </p>

                    <h1 class="signin-main-title">
                        Welcome back.<br>
                        Your next step is waiting.
                    </h1>

                    <p class="signin-description">
                        Pick up where you left off and continue
                        exploring opportunities built around your profile.
                    </p>

                </div>
                """
            )


    # =================================
    # RIGHT SIDE
    # =================================

    with right:

        with st.container(key="signin_right"):

            # Back to Home
            if st.button(
                "",
                icon=":material/arrow_back:",
                key="back_home_signin",
                type="tertiary",
            ):
                st.switch_page("app.py")


            # Heading
            st.html(
                """
                <div class="signin-form-heading">

                    <p class="signin-eyebrow">
                        WELCOME BACK TO CAREERCOMPASS
                    </p>

                    <h2>
                        Sign in to your account.
                    </h2>

                    <p>
                        Continue your CareerCompass journey.
                    </p>

                </div>
                """
            )


            # ---------------------------------
            # Form
            # ---------------------------------

            email = st.text_input(
                "Email address",
                placeholder="you@example.com",
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
            )


            # ---------------------------------
            # Sign in button
            # ---------------------------------

            if st.button(
                "Sign in",
                type="primary",
                use_container_width=True,
                key="signin_btn",
            ):

                if not email or not password:

                    st.warning(
                        "Please enter your email and password."
                    )

                else:

                    try:

                        with st.spinner(
                            "Signing you in..."
                        ):

                            response = requests.post(
                                f"{API_BASE}/api/auth/login",
                                json={
                                    "email": email,
                                    "password": password,
                                },
                                timeout=15,
                            )


                        if response.status_code == 200:

                            data = response.json()

                            token = data["access_token"]


                            # ---------------------------------
                            # Load saved user profile
                            # ---------------------------------

                            me_response = requests.get(
                                f"{API_BASE}/api/auth/me",
                                headers={
                                    "Authorization": f"Bearer {token}"
                                },
                                timeout=15,
                            )


                            if me_response.status_code == 200:

                                me_data = me_response.json()


                                # Store auth info
                                st.session_state["token"] = token

                                st.session_state["user_email"] = (
                                    me_data["email"]
                                )

                                st.session_state["user_id"] = (
                                    me_data["id"]
                                )


                                # Store profile if available
                                if me_data.get("profile"):

                                    st.session_state["profile"] = (
                                        me_data["profile"]
                                    )


                                # Go to Dashboard
                                st.switch_page(
                                    "pages/dashboard.py"
                                )


                            else:

                                st.error(
                                    "Could not load your profile. "
                                    "Please try again."
                                )


                        elif response.status_code == 401:

                            st.error(
                                "Invalid email or password. "
                                "Please try again."
                            )


                        else:

                            st.error(
                                "Sign in failed "
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
            # Create Account
            # ---------------------------------

            with st.container(
                key="signin_signup_row",
                horizontal=True,
                horizontal_alignment="center",
                vertical_alignment="center",
            ):

                st.html(
                    """
                    <span class="signin-create-text">
                        Don't have an account?
                    </span>
                    """
                )

                if st.button(
                    "Create account",
                    type="tertiary",
                    key="go_signup",
                ):
                    st.switch_page(
                        "pages/sign_up.py"
                    )