from pathlib import Path
import streamlit as st
import base64


# ---------------------------------
# Page settings
# ---------------------------------

st.set_page_config(
    page_title="CareerCompass | Home",
    page_icon=":material/explore:",
    layout="wide"
)


# ---------------------------------
# Files
# ---------------------------------

ASSETS = Path(__file__).parent / "assets"

st.html(ASSETS / "home.css")

logo = ASSETS / "logo.png"


# ---------------------------------
# Popup
# ---------------------------------

@st.dialog("Your next step")
def account_notice():

    st.write(
        "The account experience is coming next."
    )

    st.caption(
        "For now, explore our services and "
        "how CareerCompass works below."
    )

    if st.button(
        "Back to Home",
        type="primary"
    ):
        st.rerun()


# =================================
# 2. HERO
# =================================

with st.container(
    key="home_hero"
):

    left, right = st.columns(
        [1.12, 1],
        gap="large",
        vertical_alignment="center"
    )


    # LEFT SIDE
    with left:

        st.html(
            """
            <div id="home" class="cc-badge">
                <span></span>
                Your career, navigated with confidence
            </div>
            """
        )

        st.html(
            """
            <h1 class="cc-hero-title">
                Navigate your career journey
                with clarity and purpose
            </h1>
            """
        )

        st.html(
            """
            <p class="cc-hero-copy">
                CareerCompass brings jobs,
                freelance opportunities,
                and certification planning into one
                professional platform designed to help
                you grow at every stage of your career.
            </p>
            """
        )


        with st.container(
            horizontal=True,
            vertical_alignment="center"
        ):

            if st.button(
                "Get started",
                key="hero_start",
                type="primary",
                icon=":material/arrow_forward:"
            ):
                st.switch_page("pages/sign_up.py")

            st.html(
                """
                <a
                    class="cc-outline-link"
                    href="#services"
                >
                    Explore services
                </a>
                """
            )


    # RIGHT SIDE
    with right:

        st.image(
            logo,
            width="stretch"
        )


# =================================
# 3. SERVICES
# =================================

with st.container(
    key="home_services"
):

    # Section title
    st.html(
        """
        <div
            class="cc-section-heading"
            id="services"
        >
            <h2>Our Services</h2>

            <p>
                Everything you need to advance
                your career in one place
            </p>
        </div>
        """
    )


    services = [
        {
            "icon": "work",
            "title": "Jobs",
            "description":
                "Discover full-time and remote positions "
                "matched to your skills, experience, "
                "and career profile.",
            "button": "Browse jobs"
        },

        {
            "icon": "folder_open",
            "title": "Freelance",
            "description":
                "Find freelance projects that fit your "
                "expertise, showcase your strengths, "
                "and grow your professional experience.",
            "button": "Explore projects"
        },

        {
            "icon": "workspace_premium",
            "title": "Certifications",
            "description":
                "Prepare for your next certification "
                "with a personalized study plan tailored "
                "to your level and exam timeline.",
            "button": "View certifications"
        }
    ]


    columns = st.columns(
        3,
        gap="medium"
    )


    for i in range(3):

        service = services[i]

        with columns[i]:

            with st.container(
                border=True,
                key=f"home_service_{i}",
                height="stretch"
            ):

                              # Icon
                icon_paths = {
                    "Jobs": (
                        '<rect x="3" y="7" width="18" height="14" rx="2"/>'
                        '<path d="M8 7V3h8v4M8 7v14M16 7v14"/>'
                    ),
                    "Freelance": (
                        '<rect x="3" y="6" width="18" height="15" rx="2"/>'
                        '<path d="M8 6V3h8v3M8 12v3M12 10v7M16 12v3"/>'
                    ),
                    "Certifications": (
                        '<circle cx="12" cy="8" r="6"/>'
                        '<path d="m8 13-2 9 6-3 6 3-2-9"/>'
                    ),
                }

                svg = f"""
                <svg xmlns="http://www.w3.org/2000/svg"
                     width="24" height="24" viewBox="0 0 24 24"
                     fill="none" stroke="#1597E5"
                     stroke-width="1.7"
                     stroke-linecap="round"
                     stroke-linejoin="round">
                    {icon_paths[service["title"]]}
                </svg>
                """

                encoded_icon = base64.b64encode(
                    svg.encode("utf-8")
                ).decode("ascii")

                st.html(f"""
                    <div style="
                        width:52px; height:52px;
                        background:#EDF7FD;
                        border-radius:9px;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                    ">
                        <img
                            src="data:image/svg+xml;base64,{encoded_icon}"
                            alt=""
                            width="24"
                            height="24"
                            style="display:block;"
                        >
                    </div>
                """)


                # Text
                st.subheader(
                    service["title"]
                )

                st.write(
                    service["description"]
                )



# =================================
# 4. HOW IT WORKS
# =================================

with st.container(
    key="home_how"
):

    st.html(
        """
        <div
            class="cc-section-heading"
            id="how-it-works"
        >
            <h2>How It Works</h2>

            <p>
                Three simple steps to get started
            </p>
        </div>
        """
    )


    steps = [
        {
            "icon": "person_add",
            "title": "Create Your Profile",
            "description":
                "Upload your CV and review your "
                "personal details, education, experience, "
                "skills, and certifications."
        },

        {
            "icon": "search",
            "title": "Discover Opportunities",
            "description":
                "See jobs and freelance projects selected "
                "for your profile, with clear reasons "
                "for each match."
        },

        {
            "icon": "trending_up",
            "title": "Grow Your Career",
            "description":
                "Explore your next career move and create "
                "a focused study plan for your next "
                "certification."
        }
    ]


    step_icons = {
        "person_add": (
            '<circle cx="10" cy="7" r="4"/>'
            '<path d="M3 21v-2a7 7 0 0 1 14 0v2'
            'M20 8v6M17 11h6"/>'
        ),
        "search": (
            '<circle cx="10" cy="10" r="7"/>'
            '<path d="m15 15 6 6"/>'
        ),
        "trending_up": (
            '<path d="m3 18 6-7 4 3 8-10M15 4h6v6"/>'
        ),
    }

    step_cards = []

    for i, step in enumerate(steps):
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="32" height="32" viewBox="0 0 24 24"
             fill="none" stroke="white" stroke-width="1.7"
             stroke-linecap="round" stroke-linejoin="round">
            {step_icons[step["icon"]]}
        </svg>
        """

        encoded_icon = base64.b64encode(
            svg.encode("utf-8")
        ).decode("ascii")

        step_cards.append(f"""
            <div class="cc-how-step">
                <div class="cc-how-icon">
                    <img
                        src="data:image/svg+xml;base64,{encoded_icon}"
                        width="32" height="32" alt=""
                    >
                    <span class="cc-how-number">{i + 1}</span>
                </div>
                <h3>{step["title"]}</h3>
                <p>{step["description"]}</p>
            </div>
        """)

    st.html(
        '<div class="cc-how-grid">'
        + "".join(step_cards)
        + '</div>'
    )

# =================================
# 5. WHY CAREERCOMPASS
# =================================

with st.container(
    key="home_about"
):

    st.html(
        """
        <div
            class="cc-section-heading"
            id="about"
        >
            <h2>Why CareerCompass</h2>

            <p>
                Built for professionals
                who want to grow
            </p>
        </div>
        """
    )


    benefits = [
        {
            "icon": "target",
            "title": "Personalized Matching",
            "description":
                "Discover opportunities connected "
                "to the skills and experience in your CV."
        },

        {
            "icon": "description",
            "title": "One Complete Profile",
            "description":
                "Bring your background, qualifications, "
                "and achievements together in one place."
        },

        {
            "icon": "manage_search",
            "title": "Clear Match Insights",
            "description":
                "Understand why an opportunity fits "
                "and which skills you could strengthen."
        },

        {
            "icon": "schedule",
            "title": "Less Time Searching",
            "description":
                "Relevant roles and projects come to you, "
                "without lengthy searches or filters."
        },

        {
            "icon": "folder_open",
            "title": "Showcase Your Work",
            "description":
                "Include projects and professional links "
                "to give your experience more context."
        },

        {
            "icon": "workspace_premium",
            "title": "Career Growth",
            "description":
                "Turn your certification goal into "
                "clear priorities and a weekly study plan."
        }
    ]


    # Two rows
    for row in range(2):

        columns = st.columns(
            3,
            gap="medium"
        )


        for col_index in range(3):

            item_index = row * 3 + col_index

            benefit = benefits[item_index]


            with columns[col_index]:

                with st.container(
                    border=True,
                    key=f"home_benefit_{row}_{col_index}",
                    height="stretch"
                ):

                    st.markdown(
                        f":material/{benefit['icon']}:"
                    )

                    st.markdown(
                        f"#### {benefit['title']}"
                    )

                    st.write(
                        benefit["description"]
                    )


# =================================
# 6. CALL TO ACTION
# =================================

with st.container(
    key="home_cta",
    horizontal_alignment="center"
):

    st.header(
        "Ready to take the next step?",
        text_alignment="center"
    )

    st.write(
        "Join CareerCompass today and start "
        "navigating your career with purpose."
    )

    if st.button(
        "Get started",
        key="bottom_start",
        type="primary",
        icon=":material/arrow_forward:"
    ):
        st.switch_page("pages/sign_up.py")


# =================================
# 7. FOOTER
# =================================

with st.container(
    key="home_footer"
):

    brand, platform, company, connect = st.columns(
        [1.5, 1, 1, 1],
        gap="large"
    )


    # Brand
    with brand:

        st.image(
            logo,
            width="stretch"
        )

        st.caption(
            "Navigate your career journey "
            "with confidence."
        )


    # Platform
    with platform:

        st.markdown(
            "**Platform**"
        )

        st.markdown(
            """
            [Jobs](#services)

            [Freelance](#services)

            [Certifications](#services)
            """
        )


    # Company
    with company:

        st.markdown(
            "**Company**"
        )

        st.markdown(
            """
            [About](#about)

            [Services](#services)

            [How it works](#how-it-works)
            """
        )


    # Next chapter
    with connect:

        st.markdown(
            "**Your next chapter**"
        )

        st.caption(
            "Start with your CV. "
            "Find your direction."
        )

        if st.button(
            "Create your profile",
            key="footer_start",
            type="tertiary"
        ):
            st.switch_page("pages/sign_up.py")


    st.caption(
        "© 2026 CareerCompass. "
        "All rights reserved."
    )