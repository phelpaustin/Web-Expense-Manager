from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.api.expenses import fetch_expenses
from app.logic import budgets as budgets_logic

router = APIRouter()


class BudgetSet(BaseModel):
    category: str = Field(min_length=1)
    amount: float = Field(gt=0)


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
