# Expense Webpage

A non-Streamlit rewrite of the Expense Tracker Dashboard.

- **backend/** — FastAPI (Python). Exposes your expense logic as a REST API.
- **frontend/** — React + Vite. The actual webpage users see.

The old Streamlit app in `Expense-Tracker-Dashboard/` stays in maintenance mode
and is used as a reference. Logic modules from it are ported into
`backend/app/logic/` one feature at a time.

## Mental model

```
React (frontend)  --HTTP-->  FastAPI (backend)  --imports-->  logic modules
                                    |
                                    v
                                 database (SQLAlchemy)
```

## Project structure

```
Expense_webpage/
├── render.yaml            # backend deploy config (Render Blueprint)
├── backend/               # FastAPI + SQLAlchemy
│   ├── main.py            # app entry, CORS, startup seeding
│   ├── app/
│   │   ├── api/           # HTTP routes (auth, expenses, budgets, analytics)
│   │   ├── core/          # config + security (JWT, password hashing)
│   │   ├── db/            # engine, models, seed
│   │   └── logic/         # ported Streamlit-free logic modules
│   └── requirements.txt
└── frontend/              # React + Vite
    └── src/
        ├── App.jsx        # dashboard (gated behind auth)
        ├── AuthScreen.jsx # login / register
        ├── api/client.js  # backend calls + token handling
        └── styles/
```

## Prerequisites

- **Python 3.10+** and **Node.js 18+** (`node --version`, `python3 --version`).
- **virtualenv** — used because some systems ship Python without the `venv`
  module. Install with `pip install --user virtualenv` if missing.
- Git.

## Getting started

Clone the repo (or open the existing folder), then set up each half.

```bash
git clone https://github.com/YOU/expense-webpage.git
cd expense-webpage
```

### Backend setup

```bash
cd backend
virtualenv .venv                 # or: python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional; sensible defaults work locally
uvicorn main:app --reload --port 8000
```

- On first run it creates a local `expense.db` SQLite file and seeds sample
  data plus a demo user — no database setup required.
- API docs: http://localhost:8000/docs

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

- Open http://localhost:5173.
- Vite proxies `/api/*` to the backend on port 8000, so no config is needed
  locally. (For production, set `VITE_API_URL` — see Deployment.)

### First login

Use the seeded demo account, or register your own:

- **Email:** `demo@example.com`
- **Password:** `demo1234`

## Status

Done: SQLAlchemy database, JWT authentication with per-user data isolation,
expense CRUD, budget CRUD, trends/forecast and category analytics.

Ported logic modules so far: `analytics.py`, `budget_manager.py` (partial).
Remaining Streamlit modules (income, recurring, bills, AI insights, OCR, etc.)
follow the same pattern: strip Streamlit → `app/logic/` → `app/api/` → React.

## Database

The backend uses **SQLAlchemy**, so the same code runs on SQLite locally and
Postgres in production.

- **Local (default):** a `expense.db` SQLite file is created automatically on
  first run and seeded with sample data. No setup needed.
- **Supabase / Postgres:** create a project at supabase.com, then in
  `backend/.env` set:

  ```
  DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
  ```

  Restart the backend — tables are created and seeded automatically. Nothing
  else changes.

Tables: `expenses`, `budgets` (see `backend/app/db/models.py`).

## Authentication

Every data endpoint requires a logged-in user, and each user only sees their
own expenses and budgets (JWT bearer tokens).

- **Register or log in** on the first screen. The token is stored in the
  browser and sent on every request.
- **Demo account** (seeded automatically): `demo@example.com` / `demo1234`.
- In production, set a strong `SECRET_KEY` in `backend/.env`
  (e.g. `openssl rand -hex 32`). The default is for local dev only.

Auth endpoints: `POST /api/auth/register`, `POST /api/auth/login`,
`GET /api/auth/me`.

## Deployment

Managed, free-tier stack (no server to maintain):

| Piece | Host |
|-------|------|
| Database | Supabase (Postgres) |
| Backend (FastAPI) | Render — uses `render.yaml` |
| Frontend (React) | Vercel — set Root Directory to `frontend` |
| Domain / DNS | Cloudflare (optional) |

Required environment variables in production:

- **Backend (Render):**
  - `DATABASE_URL` — Supabase connection string.
  - `SECRET_KEY` — strong random value (`openssl rand -hex 32`).
  - `CORS_ORIGINS` — the frontend URL, e.g. `https://your-app.vercel.app`.
- **Frontend (Vercel):**
  - `VITE_API_URL` — the backend URL, e.g. `https://expense-backend.onrender.com`.

Deploy flow: push to GitHub → Render deploys the backend from `render.yaml` →
Vercel deploys the frontend → set `CORS_ORIGINS` to the Vercel URL. After the
first setup, every `git push` auto-redeploys both.
