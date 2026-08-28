from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.budgets import fetch_budgets
from app.api.options import get_or_create_options
from app.api.expenses import fetch_expenses
from app.db.database import get_db
from app.db import models
from app.logic import alerts as alerts_logic
from app.logic import budgets as budgets_logic
from app.logic.budgets import TOTAL_BUDGET_KEY

router = APIRouter()


@router.get("/alerts")
def get_alerts(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id)
    budgets = fetch_budgets(db, user.id)
    opts = get_or_create_options(db, user.id)

    category_statuses = budgets_logic.calculate_budget_status(expenses, budgets)
    period_status = budgets_logic.period_budget_status(
        expenses, budgets.get(TOTAL_BUDGET_KEY), opts.budget_period, opts.budget_rollover
    )
    return alerts_logic.generate_alerts(category_statuses, period_status)
