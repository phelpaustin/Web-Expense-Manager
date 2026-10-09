# Expense Manager

A personal and shared expense manager built with React, Vite, FastAPI, and SQLAlchemy.

## Features

- Record, edit, search, filter, paginate, import, and export expenses. CSV and Excel imports support up to 10 MB and 10,000 rows; duplicate rows are skipped.
- View spending trends, category breakdowns, forecasts, price history, cash flow, and financial metrics.
- Set category and overall budgets, choose weekly, monthly, or annual tracking, and optionally carry unused or overspent amounts between periods.
- Track income, recurring expenses, pending bills, manual bills, and receipts. Receipt upload supports PDF, JPEG, and PNG files up to 10 MB; field extraction is best-effort.
- Organize shared expenses in Expense Spaces with owner, admin, editor, and viewer roles. Members can invite people by email.
- Track trips as separate shared spaces, with trip budgets, currencies, expenses, and equal-share settlement summaries.
- Use password sign-in with email verification and password reset, or optionally enable Google sign-in.

## Project layout

```text
backend/
  main.py                 FastAPI application and startup
  app/api/                API routes
  app/core/               Configuration, authentication, email, uploads, FX
  app/db/                 SQLAlchemy models, database access, and seeding
  app/logic/              Expense, budget, analytics, and other business logic
  alembic/                Database migrations
frontend/
  src/pages/              React pages
  src/hooks/              Data and mutation hooks
  src/api/client.js       API client
render.yaml               Render backend blueprint
```

## Run locally

Requirements: Python 3.10 or newer and Node.js 18 or newer.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

SQLite is the default database. On startup, Alembic applies migrations. A fresh local database is seeded with sample expenses and the demo account:

- Email: `demo@example.com`
- Password: `demo1234`

The demo account is for local development. Production databases are not seeded with it unless `DEMO_PASSWORD` is explicitly configured.

The API health check is at <http://localhost:8000/api/health>; interactive API documentation is at <http://localhost:8000/docs>.

### Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. During development, Vite proxies `/api` requests to `http://localhost:8000`. To point the frontend at another API, set `VITE_API_URL` in `frontend/.env` (for example, `VITE_API_URL=https://expense-backend.onrender.com`).

## Authentication and email

New password-based accounts must verify their email address before signing in. The verification link lets the user choose a name and password. If no email provider is configured locally, the verification and password-reset message is logged by the backend; open its link in the browser.

Passwords must be at least 12 characters and fit bcrypt's 72-byte limit. Existing accounts remain verified through the email-verification migration. Google sign-in can be enabled by setting the same OAuth client ID in backend `GOOGLE_CLIENT_ID` and frontend `VITE_GOOGLE_CLIENT_ID`.

Password reset links expire after 30 minutes. Access tokens expire after seven days; logging out, changing the password, or resetting it revokes existing sessions.

For local email delivery, configure either Resend or SMTP in `backend/.env`:

```dotenv
FRONTEND_URL=http://localhost:5173
RESEND_API_KEY=re_your_api_key
EMAIL_FROM=no-reply@yourdomain.com
```

Alternatively configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM`. For production, set `FRONTEND_URL` to the deployed frontend origin, without a trailing slash, so verification and reset links return to the right site.

## Expense Spaces and trips

An Expense Space is a shared expense area, such as a household, business, rental, or custom space. Membership is independent for each space. Owners can manage the space and members; admins can invite members; editors can add expenses and edit their own; viewers can read the space.

Trips are their own Expense Spaces. A trip can optionally be filed under a non-trip Expense Space, while its membership remains separate. Inviting someone to a trip does not give them access to its parent space. Trip expenses can use different currencies; summaries and settlement are shown in the trip currency when rates are available.

## Budgets, currencies, and recurring expenses

Budgets are stored as monthly amounts. The selected weekly, monthly, or annual view allocates that amount to the current period; rollover can carry the net of prior budgets and spending forward. Dashboard alerts can be viewed in-app and optionally sent as a daily email digest.

Every amount keeps the currency it was entered in. Currencies are validated on write: only currencies with a published Frankfurter rate are accepted, so a record can never make the dashboards unusable.

**Where a currency comes from.** Each expense, income entry, recurring template, and bill stores its own currency. When you don't pick one, it defaults to the Expense Space's currency (for expenses filed under a space) or to your base currency. A space's currency is chosen when it is created and only sets that default for *new* expenses: changing it later never alters existing expenses, and a trip's currency is the currency its summary and settlement are reported in. Budgets are stored in the currency they were set in (you can pick it when creating one) and converted for display, so changing your base or display currency never silently reinterprets them.

**Base currency vs display currency.** Two separate settings. The *base currency* (Settings) is only the default for new records. The *display currency* is the currency every total, budget, bill ledger, income summary, metric, and alert is shown in; it follows your base currency until you choose one, and can be switched from the "View in" selector in the top bar or in Settings. Switching either one never changes stored data, because every record keeps the currency it was entered in and conversion happens when it is read.

**How conversion works.** Analytics, budgets, metrics, bills, and trip summaries convert each record into the reporting currency using the exchange rate **for the record's own date** (weekends and holidays use the previous business day's rate). Final historical rates never change, so they are cached permanently in the `fx_rates` table and later requests make no network call. Rates for today, the future, and any weekend not yet followed by a published business day are provisional: they are held in memory briefly and never stored. If a historical rate cannot be loaded (for example during a provider outage), the latest rate is used instead and the exact rate is picked up on a later request. A record whose currency has no rate at all is left out of aggregates and counted in the dashboard warning rather than failing the page. Budgets for a past month convert at that month's end-of-month rate; the current period uses the latest rate. A trip's settlement is never guessed: if any trip expense can't be converted, the settlement lists those expenses instead of showing possibly wrong balances.

Recurring templates support daily, weekly, bi-weekly, monthly, quarterly, and yearly schedules. Calendar-based schedules preserve their original date, including month-end schedules. Users can apply an individual template, apply all due templates, or backfill past occurrences. The Auto-post option is saved on the template, but automatic background posting is not currently scheduled; use the apply controls in the Recurring page.

## Bills and receipts

Pending bills can be entered manually, imported from CSV or Excel bank statements, or created from an uploaded receipt. Bulk-import rows matching an existing expense or bill are marked as possible duplicates for review. Receipts can be PDFs, JPEGs, or PNGs. PDF text extraction works without an OCR system package; image OCR also requires the Tesseract system binary and may not be available on the default Render runtime.

## Database

SQLAlchemy supports SQLite for local development and PostgreSQL for deployment. Alembic migrations run when the backend starts. Monetary database columns use fixed-precision numeric types.

To use PostgreSQL locally, set `DATABASE_URL` in `backend/.env`, for example:

```dotenv
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
```

Use the connection string supplied by your database provider. Do not commit `.env` files or production credentials.

## Account deletion

Deleting an account removes its personal expenses, budgets, income, recurring templates, bills, receipts, options, and legacy trip records. Expenses in shared spaces are retained as financial history with the creator reference cleared; the UI labels those records **Deleted user**. Owned spaces transfer to an existing member when possible, or remain as ownerless historical containers. Deletion is performed in one database transaction.

## Deploy

The repository includes a Render Blueprint for the FastAPI backend. The frontend can be deployed to Vercel with its root directory set to `frontend`.

Configure these production values:

| Setting | Where | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Render | PostgreSQL connection string |
| `SECRET_KEY` | Render | Strong, private signing key; Render Blueprint generates one |
| `CORS_ORIGINS` | Render | Exact deployed frontend origin, such as `https://your-app.vercel.app` |
| `FRONTEND_URL` | Render | Deployed frontend origin used in email links |
| `RESEND_API_KEY`, `EMAIL_FROM` | Render | Email delivery through Resend; SMTP settings can be used instead |
| `VITE_API_URL` | Vercel | Backend origin, such as `https://expense-backend.onrender.com` |

Do not use the development `SECRET_KEY` value from `.env.example` in production. Generate a private key with `openssl rand -hex 32` if setting it manually. Set `FRONTEND_URL` without a trailing slash. Password sign-up requires working email delivery in production.

Optional settings:

- `GOOGLE_CLIENT_ID` on Render and `VITE_GOOGLE_CLIENT_ID` on Vercel enable Google sign-in.
- `DEMO_PASSWORD` creates a production demo account; leave it unset for normal deployments.
- `CRON_SECRET` enables the protected `POST /api/alerts/send-digest` endpoint.

To schedule the alert digest using the included GitHub Actions workflow, add repository secrets `ALERT_DIGEST_URL` (the full endpoint URL) and `CRON_SECRET` (matching the Render environment value). The workflow runs daily at 07:00 UTC and can also be started manually.

## API overview

All application data routes require a bearer token. Authentication routes cover registration, email verification, login, Google sign-in, password reset/change, logout, and account deletion. Feature routes cover expenses, budgets, analytics, income, recurring templates, bills and receipts, settings, alerts, trips, and Expense Spaces. See `/docs` on a running backend for the complete request and response schemas.
