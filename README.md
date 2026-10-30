# Expense Manager

A personal and shared expense manager built with React, Vite, FastAPI, and SQLAlchemy.

## Features

- Record, edit, search, filter, paginate, and export expenses (Spending page, All items). Importing is all on the **Import** page: bank statements, and files in the app's own expense format. CSV and Excel imports support up to 10 MB and 10,000 rows; duplicate rows are skipped.
- View spending trends, category breakdowns, forecasts, price history, cash flow, and financial metrics.
- Set category and overall budgets, choose weekly, monthly, or annual tracking, and optionally carry unused or overspent amounts between periods.
- Track income, recurring expenses, bills (to itemise, total only, or itemised), and receipts. Receipt upload supports PDF, JPEG, and PNG files up to 10 MB; receipts are stored, never read.
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

Create, rename, invite to and leave Expense Spaces under **Settings → Spaces & sharing** (the old `/groups` address opens it). A badge on Settings in the sidebar shows how many invitations are waiting.

An Expense Space is a shared expense area, such as a household, business, rental, or custom space. Membership is independent for each space. Owners can manage the space and members; admins can invite members; editors can add expenses and edit their own; viewers can read the space.

Trips are their own Expense Spaces. A trip can optionally be filed under a non-trip Expense Space, while its membership remains separate. Inviting someone to a trip does not give them access to its parent space. Trip expenses can use different currencies; summaries and settlement are shown in the trip currency when rates are available.

## Budgets, currencies, and recurring expenses

Budgets are stored as monthly amounts. The selected weekly, monthly, or annual view allocates that amount to the current period; rollover can carry the net of prior budgets and spending forward. Dashboard alerts can be viewed in-app and optionally sent as a daily email digest.

**Chance of going over.** Under the budget bars, each budget shows how likely it is to be exceeded by the end of its period (category budgets by month end; the total budget in its chosen period). It looks at what was spent over the *same stretch* of earlier months or weeks (the days after today's day of the month, or after today's weekday) and counts how often that was more than the room left now, so a bill that always lands on day 1 isn't mistaken for a pace. The share is nudged away from 0% and 100% because a few past periods can't prove either. It needs at least 4 earlier periods and says so otherwise. An alert is raised when the chance reaches 75%; this replaces the old straight-line "on pace" warning wherever there is enough history, and the daily digest only reacts to which alerts are active, not to the changing percentages.

Every amount keeps the currency it was entered in. Currencies are validated on write: only currencies with a published Frankfurter rate are accepted, so a record can never make the dashboards unusable.

**Where a currency comes from.** Each expense, income entry, recurring template, and bill stores its own currency. When you don't pick one, it defaults to the Expense Space's currency (for expenses filed under a space) or to your base currency. A space's currency is chosen when it is created and only sets that default for *new* expenses: changing it later never alters existing expenses, and a trip's currency is the currency its summary and settlement are reported in. Budgets are stored in the currency they were set in (you can pick it when creating one) and converted for display, so changing your base or display currency never silently reinterprets them.

**Base currency vs display currency.** Two separate settings. The *base currency* (Settings) is only the default for new records. The *display currency* is the currency every total, budget, bills list, income summary, metric, and alert is shown in; it follows your base currency until you choose one, and can be switched from the "View in" selector in the top bar or in Settings. Switching either one never changes stored data, because every record keeps the currency it was entered in and conversion happens when it is read.

**How conversion works.** Analytics, budgets, metrics, bills, and trip summaries convert each record into the reporting currency using the exchange rate **for the record's own date** (weekends and holidays use the previous business day's rate). Final historical rates never change, so they are cached permanently in the `fx_rates` table and later requests make no network call. Rates for today, the future, and any weekend not yet followed by a published business day are provisional: they are held in memory briefly and never stored. If a historical rate cannot be loaded (for example during a provider outage), the latest rate is used instead and the exact rate is picked up on a later request. A record whose currency has no rate at all is left out of aggregates and counted in the dashboard warning rather than failing the page. Budgets for a past month convert at that month's end-of-month rate; the current period uses the latest rate. A trip's settlement is never guessed: if any trip expense can't be converted, the settlement lists those expenses instead of showing possibly wrong balances.

Recurring templates support daily, weekly, bi-weekly, monthly, quarterly, and yearly schedules. Calendar-based schedules preserve their original date, including month-end schedules. Users can apply an individual template, apply all due templates, or backfill past occurrences. The Auto-post option is saved on the template, but automatic background posting is not currently scheduled; use the apply controls in the Recurring page. Above the list, the Recurring page says what all templates cost together ("3 recurring payments cost about 1,260 kr a month"), and a payment that is not monthly shows what it comes to a month.

## Bills and receipts

Bills can be added by hand, imported from CSV or Excel bank statements (`,` or `;` delimited, decimal commas, UTF-8 or Windows-1252; only money going out becomes a bill), or created from an uploaded receipt. Everything lives in one paginated list on the Bills page, and every bill is in one of three states:

- **To itemise**: not counted as spending yet.
- **Total only**: recorded as a single expense for the whole amount (category "Bills" unless you pick another), so it counts towards budgets and analytics straight away. Expenses like this are highlighted on the Expenses page (with a **Total only** badge, an **Itemise** button, and a filter).
- **Itemised**: broken down into its line items.

By default (Settings → Bills, or the toggle on the Spending page, By receipt) every new bill is recorded as **Total only** immediately, so you can itemise whenever you like. **Itemise** opens the Expenses "Add by bill" screen prefilled with the bill (date, shop, currency, total and any receipt); when you submit the items they replace the single total line in one step, so nothing is counted twice. **Undo** takes a recorded total back and returns the bill to To itemise. An itemised bill can be re-itemised too: **Edit items** opens the same screen with the bill's current items loaded (change, remove or add lines; saving replaces the old items in one step), and **Revert to total** replaces the items with a single line for the full bill amount, back to Total only. Itemised groups on the Expenses page have an **Edit items** button as well. With the setting off, bills wait in To itemise until you record or itemise them. Bills flagged as possible duplicates (same date and amount as an existing expense or bill) are never recorded automatically; review them first. Receipts stay attached through every state until you remove them or delete the bill. Deleting a bill keeps any expenses made from it.

**Every expense is under Spending, By receipt.** Expenses entered any other way (the Spending page, an import, a recurring item, "Add by bill") are filed under a bill too, so the By receipt view, the Expenses page, and all statistics, graphs, budgets, and exports show the same spending. Expenses that are not in a bill yet are adopted into one when the Bills or Expenses page loads, which also brings in everything that existed before: lines with the same shop, date, currency, and space form one bill (the same grouping the Expenses page uses), and an expense with no shop is a bill by itself, named after it. These bills are marked "from expenses", are shown as Itemised, and follow their expenses: editing an expense updates its bill (including moving it to the right bill if its shop, date, currency, or space changes), and a bill disappears with its last expense (or, if it has a receipt, goes back to To itemise so the receipt is not lost). They have **Edit items** and **Revert to total** like any other bill, but no Delete: delete the expenses to remove the bill. "Add by bill" on the Expenses page makes its bill record immediately and keeps all its lines together whatever their shop. To keep a receipt with a purchase you entered as expenses, use the receipt button on its bill. Receipts can be PDFs, JPEGs, or PNGs; they are stored as they are and never read.

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

To schedule the alert digest using the included GitHub Actions workflow, add repository secrets `ALERT_DIGEST_URL` (the full endpoint URL) and `CRON_SECRET` (matching the Render environment value). The workflow runs daily at 07:00 UTC and can also be started manually. The workflow waits for the sleeping free Render service and retries for a few minutes. GitHub stops scheduled workflows after 60 days with no commits to the repository; if digests stop, re-enable it under the Actions tab.

## API overview

All application data routes require a bearer token. Authentication routes cover registration, email verification, login, Google sign-in, password reset/change, logout, and account deletion. Feature routes cover expenses, budgets, analytics, income, recurring templates, bills and receipts, settings, alerts, trips, and Expense Spaces. See `/docs` on a running backend for the complete request and response schemas.

## Testing

Backend (pytest, uses a throwaway SQLite database and a fake exchange-rate provider, so it needs no network):

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

Frontend (vitest + Testing Library):

```bash
cd frontend
npm ci
npm test
```

GitHub Actions runs both on every push to `main` and on pull requests.

## Dashboard and Insights

**Savings** (sidebar, under Money) tracks things you are saving towards: give a goal a name, a target amount and optionally a target date, then add money as you put it aside (or take some back out). Each goal shows its progress, what it needs per month to meet its date, your pace over the last 90 days and when that pace would get you there, and whether you are on track, behind, overdue or done. It only tracks what you enter; it does not move or look at any money. Goals are personal, have their own currency, and are removed with your account.

The **Dashboard** answers "how am I doing right now?": total spent, net this month, savings rate, projected spend, budget status, the chance of going over a budget, and a small spending trend. **Insights** answers "why, and what next?" in tabs: Overview (a month compared with last month, the same month last year and your 3-month average; the biggest movers, meaning the categories and shops that rose most, fell most or are new; recurring costs, meaning what your recurring payments come to per month and per year, when each is next due and which have gone up in price; "Worth a look", meaning recent expenses far above what you usually spend in that category and entries that look entered twice, as suggestions only; a **Not a duplicate** button hides a group for good, an "N marked as not a duplicate" list brings it back with Undo, and it reappears by itself if another look-alike entry is added; "When you spend", meaning your average spending per day for each weekday and each part of the month (recurring payments left out); trend; committed vs everyday; cash flow; volatility), Forecast, Categories (what changed, category breakdown), Report (a whole year or one month: spent, income, net, change from the year or month before, a chart and table of spending by category with amounts and shares, spending by month or by day, top shops and the largest expenses, with **Download Excel** and **Download PDF** buttons; the Excel file has a sheet per section with charts, and a year also gets a category-by-month table), Members (who paid for how much in the shared spaces you pick: each member's total, share, number of expenses, average and top categories, a table of who spends on what, and the months side by side; a period menu from this month to all time; only spending filed in a shared space counts, and every member of a space can already see what is in it), Shops and Prices (a cheapest-shop-per-item list at the top: items where a shop you use less beats your usual one, for the same product, over the last 12 months by default), plus a Price rises list above it: items whose latest price at the same shop is at least 10% above what you usually paid there. The biggest few also appear in the notification bell (the daily budget email does not include them). `/prices` and `/shops` redirect to their tabs. On a computer the sidebar lists the tabs under **Insights** while you are on that page, and the chosen tab is kept in the address (`/insights?tab=report`), so reloading or sharing the link opens the same tab.

## Dashboard numbers

- Month-over-month change and volatility use **finished months only**. The in-progress month is shown in the chart but left out of those figures (the dashboard says so). Months with no spend between finished months count as zero.
- **The forecast** is for the month in progress and covers *baseline* spending: committed plus everyday, without one-offs, so one big purchase doesn't inflate it (one-offs are shown beside it). Several simple methods are tested the way they would really be used (forecast a past month from only the months before it); the most accurate wins, preferring the simpler unless another is at least 5% better, and the same errors size the range (80%, widened for few tests). It needs 3 finished months for a number, 5 to test it and 7 for a range; seasonal patterns are only considered with 27+ months. It is never negative, and the category forecasts are scaled to add up to the total.
- The category suggester matches **whole words** (plural allowed), not substrings, so "Pizza slice" is Dining rather than Transport.

## Email addresses

Emails are case-insensitive: they are trimmed and lowercased on sign-up, sign-in, Google sign-in, password reset, resend-verification and group invites. Migration `0019_lowercase_emails` lowercases existing rows. If two accounts already differ only by case they are left as they are (each may own data); lookups still resolve them, oldest account first, so you may want to merge those by hand.

## Leaving or removing a member, deleting a space

- When someone leaves a space or trip (or is removed), their own expenses in it go back to personal, so they stay editable and a trip settlement no longer counts payments from a person who is gone. Other members' expenses are untouched, and the leaver's mappings into that space are cleared.
- Deleting a space keeps every member's expenses (made personal) and un-nests child spaces/trips.
- Migration `0020_rescue_orphaned_expenses` fixes expenses already stranded this way.

## Budget alert emails: unsubscribe

- Every digest email ends with an unsubscribe link (also sent as a `List-Unsubscribe` header). It opens `/unsubscribe?token=…` on the frontend, which works without signing in; clicking the button turns the digest off for that account. The link is signed with `SECRET_KEY` and valid for a year; it can only do this one thing.
- Users can also turn the emails on or off in Settings → Data → Email. Existing users keep receiving the digest until they opt out (migration `0021_alert_digest_enabled`).
- The link uses `FRONTEND_URL`, so make sure it is set to your Vercel URL in production.

## Importing bank statements

**Import** (sidebar) is the one place for bringing data in. It has two tabs. **Expense file** loads a spreadsheet that is already in this app's expense format (what Export produces, with items, quantity, unit and brand; the old dashboard format works too): duplicates are skipped, and rows that could not be read are listed so each can be fixed and added back. **Bank statement** reads a CSV or Excel statement from your bank in four steps, and nothing is saved until the last one:

1. **Columns.** The app finds the table (banks put a title and account details above it), guesses which column is the date, description and amount, and which date format is used. You can change any of it.
2. **Money in and out.** One signed amount column (choose whether negative or positive means money out), separate money-out and money-in columns, or an amount plus a Debit/Credit column. Expenses and income are imported into their own lists. Under **Save expenses as** choose *Expenses* (each row goes straight into your expense list) or *Bills* (each row becomes a bill you can attach a receipt to and itemise later; it counts as spending straight away when Settings → Bills says so). The Bills page links here; it no longer has an importer of its own.
3. **Rules and the assistant.** A rule says "when the description or shop contains X: leave it out / treat as expense / treat as income / file under category Y" (the first matching rule wins, and *leave out* beats the others). With an Anthropic key set, you can instead type what you want ("skip transfers to my savings account", "Swish from Anna is income") and the assistant fills in the columns and rules for you to check. It only ever proposes a mapping; the preview shows exactly what it does.
4. **Preview and import.** Every row is listed with what it will become and why. Change a row's type or category, or leave it out. Rows already in your records are recognised, so importing the same statement twice adds nothing (two identical purchases within one statement are both kept). Rows are categorised from what you called the same shop or description before, then from keyword rules.

**Remember this for next time** saves the columns and rules under a name; a later file with the same column headings is then set up automatically. Up to 20 are kept per account.

What the AI sees: only the column headings, about ten sample rows (cells cut to 60 characters) and your instruction. The rest of the file is read on the server and never sent. Text inside the statement cannot give the model instructions: it is passed as data, the model can only answer with a mapping, and the mapping is validated (columns must exist, rules are plain text matches). Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) on the backend to enable it; without a key the assistant box is hidden. Assistant calls are limited to 30 per hour per visitor (`RATE_LIMIT_IMPORT_AI`).

## Exports and spreadsheet formulas

Export CSV or Excel under **Settings → App data**. The yearly/monthly report has its own Excel and PDF download on **Insights → Report**. In the PDF, characters the built-in font cannot draw (for example Japanese shop names) print as `?`; the Excel file keeps them.

Text cells in the CSV/XLSX export that start with `=`, `+`, `-` or `@` (or a tab/line break) get a leading `'`, so Excel, Sheets and LibreOffice show them as text instead of running them as formulas (a shop named `=HYPERLINK(...)` is harmless). Amounts, quantities and dates stay real numbers/dates. Importing one of our own exports (expenses or bills) removes that quote again, so the original text comes back.

## Receipts

Uploading a receipt (Bills → 📤 Upload receipt) only **stores** the PDF or photo. Nothing is read from it: no shop, date or amount is guessed. It becomes a bill under "To itemise", named after the file and with no amount, and nothing counts as spending until you record its total or itemise it. Itemising fills the bill's amount, date and shop from the items you typed. To keep a receipt with a bill you already have, use the 📎 button on that bill.

### Where receipt files are stored

By default the file is kept in the database (`receipts.data`). With `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` set, **new** receipts go to a private Supabase Storage bucket and the database keeps only a pointer (`receipts.storage_key`). Downloads still pass through the app (`GET /api/pending-bills/{id}/receipt`), so the bucket never needs to be public and the usual login and ownership checks apply. Receipts in either place are readable side by side. Replacing or deleting a receipt, deleting a bill, or deleting an account removes the file from the bucket too.

Set up:

1. Supabase → Storage → **New bucket**, name `receipts`, **Public bucket: off**.
2. Supabase → Project Settings → API: copy the project URL and the `service_role` key (a server secret).
3. On Render set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (optionally `SUPABASE_RECEIPTS_BUCKET`), then redeploy. Migration `0024` runs on startup.
4. Prove it works: `python -m app.scripts.migrate_receipts --check` (uploads, downloads and deletes a test object).
5. Move the existing receipts: `python -m app.scripts.migrate_receipts --dry-run`, then without `--dry-run`. It uploads each file, reads it back, compares, and only then switches the row to its key and clears the database bytes. It is safe to stop and re-run, and a receipt that fails is left untouched. Use `--keep-data` to copy without clearing, and `--purge-copied` later to clear the database copies.
6. Afterwards run `VACUUM FULL receipts;` in the Supabase SQL editor (in a quiet moment, it locks the table briefly) so Postgres gives the space back.

An object that no row points at (rare: the database write failed right after an upload, or a clean-up delete failed) costs a little storage and nothing else. To find and remove them, run the sweep from a machine with the same `DATABASE_URL` and Supabase variables as the app:

```
python -m app.scripts.migrate_receipts --sweep            # list only, changes nothing
python -m app.scripts.migrate_receipts --sweep --delete   # remove the orphans
```

It lists the whole bucket and compares it with the keys the `receipts` table points at. Objects younger than an hour (`--grace-minutes`) or with no usable timestamp are never touched, so an upload in progress is safe. It refuses to delete if the database references no receipts at all while the bucket has files, which usually means `DATABASE_URL` is pointing at the wrong database (`--force` overrides). It also reports receipts whose file is missing from the bucket, without changing anything. Run it without `--delete` first and read the list.
