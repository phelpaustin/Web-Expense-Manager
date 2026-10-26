# Web-Expense-Manager

FastAPI + SQLAlchemy backend (`backend/`), React 18 + Vite frontend (`frontend/`).
Deploys: backend on Render (`render.yaml`), frontend on Vercel, Postgres on Supabase (SQLite locally).

## Commands
- Backend tests: `cd backend && python -m pytest -q` (SQLite temp DB, FX provider is faked; ~2 min)
- One backend test file: `python -m pytest -q tests/test_bill_sync.py`
- Frontend tests: `cd frontend && npm test` (vitest + jsdom)
- Frontend build: `cd frontend && npm run build`
- Run locally: `cd backend && uvicorn main:app --reload` (port 8000); `cd frontend && npm run dev` (5173, proxies /api)

## Where things are
- `backend/` – FastAPI app: `main.py`, `app/api` (routers), `app/logic` (pure business rules), `app/core`, `app/db`, `alembic/`, `tests/`. Details, map and backend conventions: `backend/CLAUDE.md`.
- `frontend/` – React app: `src/api/client.js` (only place that calls `fetch`), `hooks/`, `pages/`, `components/`. Details and map: `frontend/CLAUDE.md`.

## Conventions (cross-cutting)
- Money is `Decimal` / `Numeric(12,2)`; never use floats for amounts. More money, currency and data rules are in `backend/CLAUDE.md`.
- Tests accompany behaviour changes: backend in `backend/tests/`, frontend in `frontend/src/__tests__/`.

## Token-saving rules (read this before exploring)
- Do NOT read `frontend/package-lock.json`, `backend/alembic/versions/*` (unless adding or debugging a migration), `**/__tests__/*` and `backend/tests/*` (unless asked, or editing the code they cover), `frontend/src/styles/index.css`, `dist/`, `node_modules/`.
- Use Grep to locate code, then read only the needed line range. Large files: `expenses.py`, `bills.py`, `client.js`.
- Don't run the full backend suite for a small change; run the matching test file, then the full suite once at the end.
- Don't print whole command output; pipe through `tail`/`head`.
- `README.md` is long; `backend/CLAUDE.md` and `frontend/CLAUDE.md` are enough for orientation.
