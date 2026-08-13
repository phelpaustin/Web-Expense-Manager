import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models

router = APIRouter()


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    category: str
    description: str
    amount: float


class ExpenseCreate(BaseModel):
    date: datetime.date
    category: str = Field(min_length=1)
    description: str = ""
    amount: float = Field(gt=0)


class ExpenseUpdate(BaseModel):
    date: datetime.date | None = None
    category: str | None = Field(default=None, min_length=1)
    description: str | None = None
    amount: float | None = Field(default=None, gt=0)


def fetch_expenses(db: Session, user_id: int) -> list[dict]:
    """Shared accessor: a user's expenses as plain dicts for the logic modules."""
    rows = (
        db.query(models.Expense)
        .filter(models.Expense.user_id == user_id)
        .order_by(models.Expense.date)
        .all()
    )
    return [
        {
            "id": r.id,
            "date": r.date,
            "category": r.category,
            "description": r.description,
            "amount": r.amount,
        }
        for r in rows
    ]


def _get_owned_or_404(db: Session, expense_id: int, user_id: int) -> models.Expense:
    expense = db.get(models.Expense, expense_id)
    if expense is None or expense.user_id != user_id:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Expense)
        .filter(models.Expense.user_id == user.id)
        .order_by(models.Expense.date)
        .all()
    )


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = models.Expense(user_id=user.id, **payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = _get_owned_or_404(db, expense_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = _get_owned_or_404(db, expense_id, user.id)
    db.delete(expense)
    db.commit()


@router.get("/expenses/summary")
def expenses_summary(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id)
    total = sum(e["amount"] for e in expenses)
    by_category: dict[str, float] = {}
    for e in expenses:
        by_category[e["category"]] = round(by_category.get(e["category"], 0.0) + e["amount"], 2)
    return {"total": round(total, 2), "count": len(expenses), "by_category": by_category}
