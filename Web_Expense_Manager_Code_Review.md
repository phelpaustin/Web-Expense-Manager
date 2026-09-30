# Web Expense Manager — Code Review

**Repository:** `phelpaustin/Web-Expense-Manager`  
**Branch reviewed:** `main`  
**Review date:** 2026-09-30

## Executive Summary

The latest version is a substantial improvement over the previous review.

Several previously identified issues have been addressed, including:

- Frontend `App.jsx` split into domain-specific hooks
- Server-side expense pagination
- Improved group/editor permissions
- Invite rate limiting
- Multi-currency support and FX conversion
- Tighter CORS configuration
- Receipt OCR support
- Budget alert emails
- More production-oriented deployment configuration

The application is now beyond a basic expense CRUD application. It has shared Expense Spaces, permissions, trips, recurring expenses, bills, currencies, OCR, alerts, and authentication.

The next phase should focus less on adding features and more on **financial correctness, security, testing, reliability, and production hardening**.

---

# 1. Priority Summary

## 🔴 High Priority — Address before calling it production-ready

- [ ] Replace `Float` with `Decimal/Numeric` for monetary values
- [ ] Prevent password-reset token reuse
- [ ] Improve JWT/session revocation strategy
- [ ] Validate uploaded files using file signatures, not only MIME type
- [ ] Validate currencies against supported ISO 4217 codes
- [ ] Add backend authentication and authorization tests
- [ ] Add shared-space permission tests
- [ ] Test account deletion with shared data
- [ ] Make multi-step database mutations atomic
- [ ] Add CI for backend and frontend

## 🟠 Medium Priority — Strongly recommended

- [ ] Support historical FX rates
- [ ] Prevent repeated alert emails
- [ ] Add Expense Space hierarchy cycle detection
- [ ] Add audit history
- [ ] Add soft-delete/undo for financial records
- [ ] Move large analytics aggregations toward SQL
- [ ] Reduce full-dashboard refreshes after every mutation
- [ ] Define a production OCR strategy
- [ ] Add production error monitoring
- [ ] Improve production database pool configuration

## 🟢 Nice-to-have product improvements

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

---

# 2. What Has Improved

| Area | Status | Review |
|---|---|---|
| Frontend architecture | ✅ Improved | `App.jsx` is now primarily composition/wiring |
| Expense pagination | ✅ Added | Expense listing is paginated server-side |
| Group permissions | ✅ Improved | Owner/admin/editor/viewer rules are more explicit |
| Invite protection | ✅ Improved | Invite endpoints have rate limiting |
| Multi-currency | ✅ Added | Base-currency conversion is implemented |
| Receipt OCR | ✅ Added | PDF and optional image OCR paths exist |
| Budget alerts | ✅ Added | Alerts and email digest workflow exist |
| CORS | ✅ Improved | Explicit origins/methods/headers are configured |
| Production secret handling | ✅ Improved | Default secret is rejected in production |
| Demo account | ✅ Improved | Production demo seeding is opt-in |
| Frontend state organization | ✅ Improved | Domain-specific handler hooks are separated |

---

# 3. Detailed Findings

## 3.1 Monetary values use `Float`

### Priority: 🔴 High

The database currently uses floating-point fields for money, for example:

```python
amount = Column(Float, nullable=False)
price_per_unit = Column(Float, nullable=False)
```

This pattern also exists for budgets, income, bills, recurring expenses and trip/group budgets.

### Why this matters

Floating-point arithmetic can introduce precision errors.

This becomes more important now that the application supports currency conversion.

### Recommendation

Use SQLAlchemy `Numeric`, for example:

```python
from sqlalchemy import Numeric

amount = Column(Numeric(12, 2), nullable=False)
price_per_unit = Column(Numeric(12, 2), nullable=False)
```

Apply the same approach consistently to all monetary fields.

---

# 4. FX Conversion

## 4.1 Silent `1.0` fallback

### Priority: 🔴 High

The FX implementation currently returns `1.0` when a conversion is unavailable.

Conceptually:

```python
return get_rates(from_currency).get(to_currency, 1.0)
```

This is dangerous for financial reporting.

If an FX API request fails or a currency is unsupported, the application could effectively treat:

```text
100 INR
```

as:

```text
100 SEK
```

### Recommendation

Return an explicit unavailable state instead:

```text
same currency -> 1.0
known conversion -> actual rate
unknown/unavailable -> None
```

The UI should then clearly indicate that conversion is unavailable.

---

## 4.2 Historical FX rates

### Priority: 🟠 Medium

Current rates are used to convert historical expenses.

For example, an expense from January 2025 could be recalculated using a 2026 exchange rate.

This means historical reports can change over time.

### Recommendation

Decide on one of these models:

1. Current-rate reporting
2. Transaction-date FX
3. Store the exchange rate used at transaction creation

For a serious expense tracker, transaction-date FX is preferable.

Possible fields:

```text
original_amount
original_currency
exchange_rate
converted_amount
conversion_date
```

---

# 5. Authentication and Sessions

## 5.1 Password-reset token reuse

### Priority: 🔴 High

Reset tokens expire after a period, but there is no clear one-time-use mechanism.

After a successful reset, the token could potentially remain valid until expiration.

### Recommendation

Add a password reset version/token version to the user.

Example:

```text
password_reset_version
```

Include the version in the reset token.

After successful reset:

```text
password_reset_version += 1
```

The previous token then becomes invalid.

---

## 5.2 JWT stored in localStorage

### Priority: 🔴 High

The frontend stores the authentication token in browser storage.

This exposes the token to JavaScript and therefore increases the impact of an XSS vulnerability.

### Recommendation

For a production deployment, consider:

```text
HttpOnly
Secure
SameSite
```

cookies.

This prevents normal frontend JavaScript from reading the authentication token.

---

## 5.3 No server-side session revocation

### Priority: 🟠 Medium

Access tokens can remain valid for an extended period.

Consider implementing:

```text
session table
```

or:

```text
user token/session version
```

This allows:

- Logout all devices
- Invalidate sessions after password change
- Invalidate sessions after password reset
- Explicit session management

---

# 6. File Upload Security

### Priority: 🔴 High

Receipt uploads currently rely heavily on the client-provided content type.

A malicious client can potentially claim that an arbitrary file is:

```text
application/pdf
```

or:

```text
image/png
```

### Recommendation

Validate actual file signatures/magic bytes.

Examples:

```text
PDF  -> %PDF
JPEG -> FF D8 FF
PNG  -> 89 50 4E 47
```

Also consider limiting accepted image formats instead of accepting every `image/*`.

---

# 7. OCR

## 7.1 Deployment limitation

### Priority: 🟠 Medium

Image OCR uses:

```text
pytesseract
Pillow
Tesseract system binary
```

The native Render runtime does not automatically provide the Tesseract binary.

Therefore image OCR can behave differently between local development and production.

### Recommendation

Choose one:

- Deploy using Docker and install Tesseract
- Use a hosted OCR provider
- Clearly expose OCR availability in the application

---

## 7.2 OCR confidence

### Priority: 🟠 Medium

The current shop detection assumes the first substantial receipt line is probably the shop.

This is useful as a best-effort heuristic but can produce incorrect results.

### Recommendation

Return confidence values:

```json
{
  "shop": "ICA",
  "shop_confidence": 0.81,
  "amount": 182.50,
  "amount_confidence": 0.94
}
```

Let the user confirm extracted values before committing them.

---

# 8. Budget Alerts

## 8.1 Repeated emails

### Priority: 🟠 Medium

The daily GitHub Actions workflow can send the same alert repeatedly.

Example:

```text
Monday    -> budget 110% -> email
Tuesday   -> budget 110% -> email
Wednesday -> budget 110% -> email
```

### Recommendation

Store alert state/history.

Possible model:

```text
budget_alert_events
-------------------
id
user_id
alert_type
alert_key
threshold
last_sent_at
```

Then send alerts only when:

- A threshold is crossed
- Severity changes
- A configurable cooldown expires

---

## 8.2 Cron endpoint

### Priority: 🟠 Medium

The endpoint is protected by a shared secret, which is good.

Use constant-time comparison:

```python
secrets.compare_digest(
    provided_secret,
    configured_secret
)
```

Also consider rate limiting the endpoint.

---

# 9. Analytics Performance

### Priority: 🟠 Medium

The expense list is now paginated, which is good.

However, analytics/metrics/budget/alert calculations still intentionally load the complete visible expense dataset into Python.

This is acceptable for a personal application with a small dataset.

It may become expensive when users have tens or hundreds of thousands of transactions.

### Recommendation

Move aggregation toward SQL for:

- Monthly totals
- Category totals
- Budget calculations
- Metrics
- Trend calculations

Keep Python/Pandas for calculations that genuinely require it.

---

# 10. Frontend Data Loading

### Priority: 🟠 Medium

`useAppData()` currently performs many requests together.

After many mutations, handlers call:

```javascript
await loadAll()
```

This refreshes unrelated sections too.

For example, adding one expense can cause requests for:

- Summary
- Trends
- Categories
- Budgets
- Income
- Recurring
- Bills
- Ledger
- Options
- Metrics
- Budget configuration
- Period status
- Alerts
- Trips
- Groups

### Recommendation

Move toward domain-level invalidation.

Example:

```text
Add expense
    |
    +--> refresh expense/dashboard data
    +--> refresh budget status
    +--> refresh alerts
```

rather than refreshing everything.

---

# 11. Testing

## 11.1 Backend tests

### Priority: 🔴 High

A proper test suite is now important because the application has complicated authorization rules.

Recommended structure:

```text
backend/tests/
    test_auth.py
    test_expenses.py
    test_groups.py
    test_permissions.py
    test_budgets.py
    test_currency.py
    test_import.py
    test_receipts.py
    test_recurring.py
    test_trips.py
```

---

## 11.2 Permission tests

### Priority: 🔴 High

Test all roles explicitly.

### Viewer

```text
GET shared expense -> allowed
POST expense        -> denied
PUT expense         -> denied
DELETE expense      -> denied
```

### Editor

```text
Create expense              -> allowed
Modify own expense         -> allowed
Modify another user's     -> denied
```

### Admin

```text
Modify shared expenses -> allowed
Manage members         -> allowed
Transfer ownership     -> according to policy
```

### Owner

```text
Full space management
```

---

## 11.3 Frontend tests

### Priority: 🟠 Medium

Add:

```text
Vitest
React Testing Library
```

Focus on critical behavior rather than 100% coverage.

---

# 12. CI/CD

### Priority: 🔴 High

GitHub Actions currently has an alert-digest workflow, but the repository should also have a proper CI workflow.

Recommended:

```text
.github/workflows/ci.yml
```

Backend:

```text
install dependencies
ruff
tests
migration checks
```

Frontend:

```text
npm ci
lint
tests
build
```

This prevents broken code from reaching production.

---

# 13. Expense Space Hierarchy

### Priority: 🟠 Medium

The application supports:

```text
parent_group_id
```

and local parent mappings.

The hierarchy needs protection against cycles such as:

```text
A -> B
B -> C
C -> A
```

and self-parenting:

```text
A -> A
```

### Recommendation

Before changing a parent:

1. Walk the ancestor chain.
2. Detect the target group.
3. Reject the update if the child would become its own ancestor.

---

# 14. Audit Trail

### Priority: 🟠 Medium

Shared expenses would benefit from an audit log.

Example:

```text
audit_log
---------
id
user_id
action
entity_type
entity_id
before_json
after_json
created_at
```

Example UI:

```text
Austin changed amount
€40 -> €400
30 Sep 2026 14:32
```

This is particularly useful for household/business shared spaces.

---

# 15. Soft Delete / Undo

### Priority: 🟠 Medium

Financial records are currently deleted permanently.

Consider:

```text
deleted_at
deleted_by
```

Then provide an undo/recycle-bin period.

This is particularly useful for accidental deletion of expenses.

---

# 16. Account Deletion and Shared Data

### Priority: 🔴 High

The application correctly removes many personal records when an account is deleted.

However, shared-space data requires a clearly defined policy.

For example, if a user created an expense in a shared space and later deletes their account:

### Option A

Keep the expense and show:

```text
Deleted user
```

### Option B

Delete all expenses created by that user.

For a shared expense application, keeping the financial record while anonymizing the creator is generally a more useful model.

Whichever policy is chosen should be implemented and tested explicitly.

---

# 17. Currency Validation

### Priority: 🔴 High

The current validation mainly checks string length.

That allows invalid values such as:

```text
banana
ABC
ABCDEFGH
```

### Recommendation

Validate against a supported ISO 4217 currency list.

This also makes FX failures much easier to reason about.

---

# 18. Database Transactions

### Priority: 🔴 High

Some operations perform multiple database actions and commits.

For example:

```text
Create user
Claim invites
Create related records
```

If one step fails after another step has committed, the database can be left partially updated.

### Recommendation

Use a transaction boundary around logically atomic operations.

Conceptually:

```text
BEGIN
    operation 1
    operation 2
    operation 3
COMMIT
```

and rollback the complete operation on failure.

---

# 19. Database Production Configuration

### Priority: 🟢 Medium

For production Postgres/Supabase, consider explicit pool settings:

```text
pool_size
max_overflow
pool_timeout
pool_recycle
pool_pre_ping
```

This is not urgent for a small personal deployment but becomes useful as concurrency grows.

---

# 20. Error Monitoring

### Priority: 🟠 Medium

Production errors currently depend heavily on server logs.

Consider adding:

```text
Sentry
```

or another error-monitoring service.

Useful information includes:

- Endpoint
- User/session context
- Exception
- Request ID
- Stack trace
- Deployment version

---

# 21. README Is Outdated

### Priority: 🟠 Medium

The README currently describes several areas as remaining/unfinished even though the repository now includes functionality such as:

- Income
- Recurring expenses
- Bills
- OCR
- Groups
- Trips
- FX conversion
- Alerts

The README should be updated to match the current product.

It should also document:

```text
ALERT_DIGEST_URL
CRON_SECRET
OCR requirements
FX behavior
Production environment variables
GitHub Actions setup
```

---

# 22. Recommended Roadmap

## Phase 1 — Security + Financial Correctness

```text
1. Replace Float with Numeric
2. Validate currencies
3. Harden file uploads
4. Fix reset-token reuse
5. Improve JWT/session handling
6. Define account-deletion semantics
7. Add transaction boundaries
```

## Phase 2 — Tests

```text
1. Authentication tests
2. Authorization tests
3. Expense CRUD tests
4. Group tests
5. Budget tests
6. Currency tests
7. Import tests
8. Receipt tests
9. Account deletion tests
```

## Phase 3 — CI/CD

```text
1. Backend lint
2. Backend tests
3. Migration validation
4. Frontend lint
5. Frontend tests
6. Frontend production build
```

## Phase 4 — Reliability

```text
1. Alert de-duplication
2. Historical FX
3. Error monitoring
4. Better OCR deployment
5. Audit trail
6. Soft delete
```

## Phase 5 — Performance

```text
1. SQL aggregation
2. Reduce API calls
3. Better caching
4. Database pool tuning
5. Background jobs where appropriate
```

## Phase 6 — Product Features

```text
1. Monthly reports
2. Cash-flow view
3. Budget history
4. Activity feed
5. Better OCR
6. Bank integrations
7. PWA/mobile
```

---

# 23. Overall Assessment

The project has moved significantly forward.

The architecture is now much more mature:

```text
React
  |
  +-- domain hooks
  |
  +-- API client
        |
        v
      FastAPI
        |
        +-- authentication
        +-- authorization
        +-- expenses
        +-- budgets
        +-- income
        +-- recurring
        +-- bills
        +-- groups
        +-- trips
        +-- OCR
        +-- FX
        +-- alerts
        |
        v
     SQLAlchemy
        |
        v
   SQLite/Postgres
```

The biggest remaining concern is no longer missing UI functionality.

It is **protecting financial correctness and shared data as the application becomes more complex**.

The next milestone should therefore be:

```text
SECURITY
   +
FINANCIAL CORRECTNESS
   +
TESTING
   +
RELIABILITY
```

before adding a large number of additional features.

## Top 10 actions I would do next

1. **Change all monetary database fields from Float to Numeric/Decimal**
2. **Add comprehensive authorization tests**
3. **Fix password-reset token reuse**
4. **Harden authentication/session management**
5. **Validate uploaded files by content/signature**
6. **Validate currencies**
7. **Add CI for backend + frontend**
8. **Define/test account deletion with shared spaces**
9. **Add alert de-duplication**
10. **Add audit logging for shared financial data**

These changes would give the current feature set a much stronger production foundation.
