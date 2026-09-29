# 🧭 CareerCompass

**CareerCompass** is an AI-powered career guidance platform that brings jobs, freelance projects, and certification planning into one place. It uses a multi-agent LangGraph system to understand your profile and deliver personalized career recommendations.

---

## What the Project Does

- **Job Search** — Finds full-time and remote positions matched to your skills and experience using `python-jobspy`.
- **Freelance Opportunities** — Discovers freelance projects via the Freelancer API tailored to your expertise.
- **Certification Planning** — Creates a personalized study plan for your next certification goal.
- **CV Upload & Parsing** — Extracts your education, skills, and experience from an uploaded PDF resume using PyMuPDF and OpenAI.
- **AI Career Assistant** — A LangGraph-powered agent graph that routes your career queries to the right specialist agent and returns a unified response.
- **User Authentication** — Secure sign-up and login using JWT and Argon2 password hashing.

The frontend is built with **Streamlit** and the backend is a **FastAPI** REST API, backed by a **SQLite** database managed with SQLModel and Alembic.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend API | FastAPI + Uvicorn |
| AI / Agents | LangGraph, LangChain, OpenAI GPT |
| Job Search | python-jobspy |
| Freelance API | Freelancer SDK |
| Web Search | Tavily |
| Database | SQLite + SQLModel + Alembic |
| Auth | PyJWT + pwdlib (Argon2) |
| CV Parsing | PyMuPDF, pypdf, OpenAI |
| Observability | LangSmith |
| Evaluation | Ragas |

---

## Requirements

- Python **3.10+**
- pip

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/career-compass.git
cd career-compass
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file in the project root (it is already in `.gitignore` and will **not** be committed). Add the following keys:

```env
# OpenAI — used for the AI agents and CV parsing
OPENAI_API_KEY=your_openai_api_key

# Freelancer — used to fetch freelance project listings
FREELANCER_ACCESS_TOKEN=your_freelancer_access_token

# Tavily — used for web search inside the agent graph
TAVILY_API_KEY=your_tavily_api_key

# Apify — used for additional scraping tasks
APIFY_API_TOKEN=your_apify_api_token

# JWT — secret key for signing authentication tokens
JWT_SECRET_KEY=your_jwt_secret_key

# LangSmith — optional, enables tracing and evaluation
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=career-compass
```

> **Never commit your `.env` file.** It is excluded by `.gitignore` by default.

### Where to get each key

| Key | Where to get it |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `FREELANCER_ACCESS_TOKEN` | [developers.freelancer.com](https://developers.freelancer.com) |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) |
| `APIFY_API_TOKEN` | [console.apify.com/account/integrations](https://console.apify.com/account/integrations) |
| `LANGSMITH_API_KEY` | [smith.langchain.com](https://smith.langchain.com) (optional) |

---

## Database Setup

Run Alembic migrations to set up the database schema:

```bash
alembic upgrade head
```

> The SQLite database file (`career_compass.db`) will be created automatically in the project root on first run if it does not already exist.

---

## Running the Project

You need to start **two servers** — the backend API and the frontend — in separate terminal windows.

### Terminal 1 — Start the FastAPI backend

```bash
uvicorn backend.main:app --reload
```

The API will be available at: `http://localhost:8000`  
Interactive API docs: `http://localhost:8000/docs`

### Terminal 2 — Start the Streamlit frontend

```bash
streamlit run frontend/app.py
```

The app will open automatically at: `http://localhost:8501`

---

## Project Structure

```
career-compass/
├── backend/
│   ├── agents/          # LangGraph specialist agents (jobs, freelance, certifications)
│   ├── graph/           # LangGraph agent graph definition
│   ├── routers/         # FastAPI route handlers (auth, career, resume, portfolio)
│   ├── database/        # SQLModel models, CRUD, and DB setup
│   ├── schemas/         # Pydantic request/response schemas
│   ├── tools/           # Agent tools (job search, Freelancer API, Tavily)
│   ├── guardrails/      # Input/output safety checks
│   ├── config.py        # Settings loaded from .env
│   ├── security.py      # JWT and password utilities
│   └── main.py          # FastAPI app entry point
├── frontend/
│   ├── app.py           # Streamlit home page
│   ├── pages/           # Streamlit multi-page app pages
│   ├── components/      # Reusable UI components
│   └── assets/          # CSS, images, logo
├── alembic/             # Database migration scripts
├── evals/               # Ragas evaluation scripts
├── data/                # Local data files (excluded from git)
├── requirements.txt
├── alembic.ini
└── .env                 # Secret keys (excluded from git)
```

---

## Limitations & Known Issues

- **SQLite only** — The project uses a local SQLite database. It is not suitable for multi-user production deployments without switching to PostgreSQL.
- **No async agents** — The LangGraph agent graph runs synchronously, which can cause the API to block on long-running queries.
- **Freelancer API rate limits** — The Freelancer SDK may hit rate limits during heavy use.
- **python-jobspy version pinned** — `python-jobspy==1.1.82` and `numpy==1.26.3` are pinned due to compatibility; upgrading may break job scraping.
- **LangSmith is optional** — If `LANGSMITH_API_KEY` is not set, tracing is disabled but the app still works.
- **Resume parsing accuracy** — CV extraction quality depends on the PDF formatting; scanned or image-based PDFs may not parse correctly.
