from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import get_or_create_options
from app.db.database import get_db
from app.db import models
from app.api.expenses import fetch_expenses
from app.logic import budgets as budgets_logic
from app.logic.budgets import TOTAL_BUDGET_KEY

router = APIRouter()


class BudgetSet(BaseModel):
    category: str = Field(min_length=1)
    amount: float = Field(gt=0)


class BudgetConfig(BaseModel):
    period: str = "Monthly"
    rollover: bool = False


def fetch_budgets(db: Session, user_id: int) -> dict:
    rows = db.query(models.Budget).filter(models.Budget.user_id == user_id).all()
    return {b.category: b.amount for b in rows}


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
    if budget is None:
        budget = models.Budget(user_id=user.id, category=payload.category, amount=payload.amount)
        db.add(budget)
    else:
        budget.amount = payload.amount
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
    month: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return budgets_logic.calculate_budget_status(
        fetch_expenses(db, user.id), fetch_budgets(db, user.id), month
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
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    total_budget = fetch_budgets(db, user.id).get(TOTAL_BUDGET_KEY)
    return budgets_logic.period_budget_status(
        fetch_expenses(db, user.id), total_budget, opts.budget_period, opts.budget_rollover
    )
