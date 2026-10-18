"""One request for everything the dashboard shows.

The dashboard used to call seven endpoints at once (summary, trends, categories, budget
status, metrics, period status, alerts). Each loaded every expense and converted it to the
reporting currency on its own, so the same work ran seven times. This endpoint does it once
and builds each part with the same functions the individual endpoints use, so the numbers
are identical (the individual endpoints remain for other callers).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.alerts import _alerts_for_user
from app.api.analytics import trends_payload
from app.api.budgets import fetch_budgets
from app.api.deps import get_current_user
from app.api.expenses import fetch_expenses_in_reporting_currency_ex, summary_payload
from app.api.income import fetch_income_in_reporting_currency
from app.api.options import get_or_create_options, reporting_currency
from app.db import models
from app.db.database import get_db
from app.logic import analytics as analytics_logic
from app.logic import budgets as budgets_logic
from app.logic import metrics as metrics_logic
from app.logic.budgets import TOTAL_BUDGET_KEY

router = APIRouter()


@router.get("/dashboard")
def dashboard(
    scope: str | None = None,
    space_ids: str | None = None,
    include_alerts: bool = True,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """summary, trends, categories, budget status, metrics, period status and (optionally)
    alerts for the chosen scope. Alerts always cover every space, whatever the scope."""
    opts = get_or_create_options(db, user.id)
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    income = fetch_income_in_reporting_currency(db, user.id)
    budgets = fetch_budgets(db, user.id)

    alerts = None
    if include_alerts:
        all_spaces = (scope is None or scope == "all") and not space_ids
        alerts = _alerts_for_user(db, user.id, expenses if all_spaces else None, budgets)

    return {
        "summary": summary_payload(expenses, unconverted, reporting_currency(opts)),
        "trends": trends_payload(expenses),
        "categories": analytics_logic.category_breakdown(expenses),
        "budgets": budgets_logic.calculate_budget_status(expenses, budgets, None),
        "metrics": metrics_logic.summary(expenses, income),
        "period_status": budgets_logic.period_budget_status(
            expenses, budgets.get(TOTAL_BUDGET_KEY), opts.budget_period, opts.budget_rollover
        ),
        "alerts": alerts,
    }
