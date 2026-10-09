import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import get_or_create_options, get_reporting_currency
from app.core.fx import normalize_convertible_currency
from app.core import fx
from app.core.money import quantize_money, MAX_MONEY
from app.db.database import get_db
from app.db import models
from app.api.expenses import fetch_expenses_in_reporting_currency
from app.logic import budgets as budgets_logic
from app.logic.budgets import TOTAL_BUDGET_KEY

router = APIRouter()


class BudgetSet(BaseModel):
    category: str = Field(min_length=1)
    amount: Decimal = Field(gt=0, le=MAX_MONEY)
    # Currency of `amount`; None = the currency budgets are currently shown in.
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None


class BudgetConfig(BaseModel):
    period: str = "Monthly"
    rollover: bool = False


def _period_end(month: str | None) -> datetime.date | None:
    """Last day of a 'YYYY-MM' month; None when absent or malformed."""
    if not month:
        return None
    try:
        first = datetime.date.fromisoformat(f"{month}-01")
    except ValueError:
        return None
    nxt = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return nxt - datetime.timedelta(days=1)


def fetch_budgets(db: Session, user_id: int, on: datetime.date | None = None) -> dict:
    """Budgets as {category: amount} in the user's reporting (display) currency.

    Each budget is stored in the currency it was set in; those in another
    currency are converted, so changing the display or base currency never
    silently reinterprets an amount. ``on`` is the date the budget applies to
    (the end of a past month): a past date uses that day's exchange rate, today
    or no date uses the latest rate. A budget that can't be converted right now
    is left out rather than shown with a wrong number.
    """
    reporting = get_reporting_currency(db, user_id)
    rows = db.query(models.Budget).filter(models.Budget.user_id == user_id).all()
    dated = on if on is not None and on < datetime.date.today() else None
    if dated is not None:
        fx.ensure_rates({(dated, b.currency) for b in rows if b.currency != reporting} | {(dated, reporting)})
    result = {}
    for b in rows:
        amount = b.amount
        if b.currency != reporting:
            rate = fx.get_rate(b.currency, reporting, dated)
            if rate is None:
                continue
            amount = quantize_money(amount * rate)
        result[b.category] = amount
    return result


@router.get("/budgets")
def get_budgets(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return fetch_budgets(db, user.id)


@router.put("/budgets")
def set_budget(
    payload: BudgetSet,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Create or update a category budget (upsert). Use the sentinel for the total."""
    budget = (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user.id, models.Budget.category == payload.category)
        .first()
    )
    # Unless the user picked one, the amount they typed is in the currency budgets are shown in.
    currency = payload.currency or get_reporting_currency(db, user.id)
    if budget is None:
        budget = models.Budget(user_id=user.id, category=payload.category, amount=payload.amount, currency=currency)
        db.add(budget)
    else:
        budget.amount = payload.amount
        budget.currency = currency
    db.commit()
    return fetch_budgets(db, user.id)


@router.delete("/budgets/{category}")
def delete_budget(
    category: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    budget = (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user.id, models.Budget.category == category)
        .first()
    )
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
    return fetch_budgets(db, user.id)


@router.get("/budgets/status")
def budgets_status(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM"),
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return budgets_logic.calculate_budget_status(
        fetch_expenses_in_reporting_currency(db, user.id, scope, space_ids),
        fetch_budgets(db, user.id, _period_end(month)),
        month,
    )


@router.get("/budgets/config")
def get_budget_config(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    return {"period": opts.budget_period, "rollover": opts.budget_rollover}


@router.put("/budgets/config")
def set_budget_config(
    payload: BudgetConfig,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    opts.budget_period = payload.period if payload.period in budgets_logic.BUDGET_PERIODS else "Monthly"
    opts.budget_rollover = bool(payload.rollover)
    db.commit()
    return {"period": opts.budget_period, "rollover": opts.budget_rollover}


@router.get("/budgets/period-status")
def budgets_period_status(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    total_budget = fetch_budgets(db, user.id).get(TOTAL_BUDGET_KEY)
    return budgets_logic.period_budget_status(
        fetch_expenses_in_reporting_currency(db, user.id, scope, space_ids), total_budget, opts.budget_period, opts.budget_rollover
    )
