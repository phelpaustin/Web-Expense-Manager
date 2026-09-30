# Implementation Plan — Code Review Follow-up

Tracks work items from [Web_Expense_Manager_Code_Review.md](Web_Expense_Manager_Code_Review.md) (2026-09-30).
Check items off as they're completed. Ordered by phase/priority per the review's roadmap (section 22).

## Phase 1 — Security + Financial Correctness (🔴 High)

- [x] Increase the minimum password length from 6 to 12 characters across backend and frontend
- [x] Replace `Float` with `Numeric/Decimal` for all monetary columns (expenses, budgets,
      income, bills, recurring, trip/group budgets, price_per_unit)
- [x] Remove explicit Decimal-to-float financial calculations from aggregation, ledger,
      budget, income, trip, metric, price, import, and OCR logic
- [x] Validate currency codes against a supported ISO 4217 list (reject `banana`, `ABC`, etc.)
- [x] Fix FX silent `1.0` fallback — return `None`/explicit "unavailable" instead of guessing a rate
- [x] Harden file uploads — validate by magic bytes/file signature (PDF `%PDF`, JPEG `FFD8FF`,
      PNG `89504E47`), not client-provided MIME type; restrict accepted image formats
- [x] Fix password-reset token reuse (add `password_reset_version`, bump on reset, embed in token)
- [x] Improve JWT/session handling — move token off `localStorage` (HttpOnly/Secure/SameSite
      cookie) and/or add server-side session revocation
- [x] Define and implement account-deletion policy for shared-space data (keep expense +
      anonymize creator vs. delete) — document and test the chosen policy
- [x] Wrap multi-step DB mutations (user creation + invite claim + related records, etc.)
      in explicit transaction boundaries with rollback on failure

## Phase 2 — Testing (🔴 High)

- [ ] `backend/tests/test_auth.py`
- [ ] `backend/tests/test_expenses.py`
- [ ] `backend/tests/test_groups.py`
- [ ] `backend/tests/test_permissions.py` — viewer/editor/admin/owner role matrix
- [ ] `backend/tests/test_budgets.py`
- [ ] `backend/tests/test_currency.py`
- [ ] `backend/tests/test_import.py`
- [ ] `backend/tests/test_receipts.py`
- [ ] `backend/tests/test_recurring.py`
- [ ] `backend/tests/test_trips.py`
- [ ] Account-deletion-with-shared-data test
- [ ] Frontend: add Vitest + React Testing Library, cover critical flows

## Phase 3 — CI/CD (🔴 High)

- [ ] `.github/workflows/ci.yml`
  - [ ] Backend: install deps, `ruff`, run tests, migration check (alembic upgrade head on
        a fresh DB)
  - [ ] Frontend: `npm ci`, lint, tests, `npm run build`

## Phase 4 — Reliability (🟠 Medium)

- [ ] Alert de-duplication — `budget_alert_events` table (threshold/last_sent_at) so digest
      only sends on threshold-cross/severity-change/cooldown, not every run
- [ ] Constant-time comparison (`secrets.compare_digest`) for the cron-secret check + rate
      limit the digest endpoint
- [ ] Historical FX — store `original_amount/original_currency/exchange_rate/converted_amount/
      conversion_date` at transaction time instead of re-converting with today's rate
- [ ] Add production error monitoring (e.g. Sentry)
- [ ] Define production OCR strategy (Docker + Tesseract, hosted OCR API, or expose
      OCR-availability in the UI) — image OCR currently silently degrades on Render
- [ ] OCR confidence scores (`shop_confidence`, `amount_confidence`) + user confirmation
      before autofill is committed
- [ ] Expense Space hierarchy cycle detection (reject self-parenting and ancestor cycles
      before updating `parent_group_id`)
- [ ] Audit log for shared-space mutations (`audit_log` table: user/action/entity/before/after)
- [ ] Soft-delete/undo for financial records (`deleted_at`/`deleted_by` + recycle-bin window)
- [ ] Database pool tuning for production Postgres (`pool_size`, `max_overflow`,
      `pool_timeout`, `pool_recycle`, `pool_pre_ping`)

## Phase 5 — Performance (🟠 Medium)

- [ ] Move heavy aggregations (monthly/category totals, budgets, metrics, trends) from
      Python/Pandas toward SQL
- [ ] Replace blanket `loadAll()` refetch-everything after mutations with domain-level
      invalidation (e.g. adding an expense only refreshes expense/budget/alert data)

## Phase 6 — Product Features (🟢 Nice-to-have)

- [ ] Monthly spending reports
- [ ] Budget history
- [ ] Cash-flow/net-worth view
- [ ] Shared-space activity feed
- [ ] Better receipt line-item OCR
- [ ] Bank integration
- [ ] Merchant normalization
- [ ] Backup/export workflow
- [ ] PWA/mobile support
- [ ] Dark mode

## Housekeeping

- [ ] Update `README.md` (remove stale "remaining Streamlit module" OCR note, document
      `ALERT_DIGEST_URL`, `CRON_SECRET`, OCR requirements, FX behavior, production env vars,
      GitHub Actions setup)
