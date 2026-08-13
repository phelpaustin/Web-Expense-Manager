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
                                 database (later)
```

## Run it locally (two terminals)

### 1. Backend

```bash
cd backend
virtualenv .venv          # (or: python3 -m venv .venv if python3-venv is installed)
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000/docs — interactive API docs (auto-generated).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the webpage. It calls the backend at `/api/*`
(Vite proxies those requests to port 8000).

## Next steps

1. Confirm both halves run and the sample expenses show up.
2. Add a database (Supabase/Postgres) and replace the sample data.
3. Port real logic modules into `backend/app/logic/`.
4. Add authentication.

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
