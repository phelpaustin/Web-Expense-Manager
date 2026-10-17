# Web-Expense-Manager

FastAPI + SQLAlchemy backend (`backend/`), React 18 + Vite frontend (`frontend/`).
Deploys: backend on Render (`render.yaml`), frontend on Vercel, Postgres on Supabase (SQLite locally).

## Commands
- Backend tests: `cd backend && python -m pytest -q` (SQLite temp DB, FX provider is faked; ~2 min)
- One backend test file: `python -m pytest -q tests/test_bill_sync.py`
- Frontend tests: `cd frontend && npm test` (vitest + jsdom)
- Frontend build: `cd frontend && npm run build`
- Run locally: `cd backend && uvicorn main:app --reload` (port 8000); `cd frontend && npm run dev` (5173, proxies /api)

## Map
- `backend/main.py` – app setup, CORS, router registration; runs Alembic migrations + seed on startup.
- `backend/app/api/` – one router per area (auth, expenses, bills, groups, trips, budgets, income, recurring, options, alerts, aliases, analytics, metrics). Thin: validation, permissions, DB access.
- `backend/app/api/bill_sync.py` – keeps every expense represented on the Bills page by "adopting" unlinked expenses into derived bills (`origin='expenses'`) and reconciling them when items change. Idempotent; unique index (user, origin_key) makes races safe.
- `backend/app/api/deps.py` – `get_current_user` (JWT + session_version + email_verified) and group role helpers (owner > admin > editor > viewer).
- `backend/app/logic/` – pure functions on plain dicts (no DB, no FastAPI): analytics, budgets, alerts, bills parsing/ledger, price tracker, categorizer, names/aliases, taxonomy, trips/settlement, currency conversion. Put business rules here and test them directly.
- `backend/app/core/` – config, security (JWT/bcrypt), email (Resend/SMTP), `fx.py` (Frankfurter rates, cached), money/parsing/upload helpers, rate limiting.
- `backend/app/db/` – `models.py`, session, seed, category cleanup. Schema changes go through `backend/alembic/versions/` (next number: 0024).
- `backend/tests/` – pytest; `conftest.py` provides `client`, `make_user`, fake FX.
- `frontend/src/api/client.js` – the only place that calls `fetch`; attaches the token, handles 401 expiry.
- `frontend/src/hooks/` – app state and handlers. `useAppData` owns fetched data and `loadAll()`; `useAuth` the session; `use*Handlers` (expense, income, recurring, bills, trip, group, budget) are mutations that call `loadAll()` afterwards.
- `frontend/src/App.jsx` – wires hooks to routes; `pages/` are screens, `components/` shared UI. `format.js` formats money.

## Conventions
- Money is `Decimal` / `Numeric(12,2)`; never use floats for amounts. Every record carries its own `currency`; totals are converted to the user's reporting currency at each row's date.
- Emails are lowercased (`app/core/emails.py`); categories are case-insensitive via `logic/taxonomy.py`.
- Tests accompany behaviour changes: backend in `backend/tests/`, frontend in `frontend/src/__tests__/`.

## Token-saving rules (read this before exploring)
- Do NOT read `frontend/package-lock.json`, `backend/alembic/versions/*` (unless adding or debugging a migration), `**/__tests__/*` and `backend/tests/*` (unless asked, or editing the code they cover), `frontend/src/styles/index.css`, `dist/`, `node_modules/`.
- Use Grep to locate code, then read only the needed line range. Large files: `ExpensesPage.jsx`, `expenses.py`, `bills.py`, `client.js`.
- Don't run the full backend suite for a small change; run the matching test file, then the full suite once at the end.
- Don't print whole command output; pipe through `tail`/`head`.
- `README.md` is long; the map above is enough for orientation.
