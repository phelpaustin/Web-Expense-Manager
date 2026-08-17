import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.logic import income as income_logic

router = APIRouter()


class IncomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    amount: float
    source: str
    note: str


class IncomeCreate(BaseModel):
    date: datetime.date
    amount: float = Field(gt=0)
    source: str = Field(min_length=1)
    note: str = ""


class IncomeUpdate(BaseModel):
    date: datetime.date | None = None
    amount: float | None = Field(default=None, gt=0)
    source: str | None = Field(default=None, min_length=1)
    note: str | None = None


def fetch_income(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(models.Income)
        .filter(models.Income.user_id == user_id)
        .order_by(models.Income.date)
        .all()
    )
    return [
        {"id": r.id, "date": r.date, "amount": r.amount, "source": r.source, "note": r.note}
        for r in rows
    ]


def _get_owned_or_404(db: Session, income_id: int, user_id: int) -> models.Income:
    row = db.get(models.Income, income_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Income entry not found")
    return row


@router.get("/income", response_model=list[IncomeOut])
def list_income(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Income)
        .filter(models.Income.user_id == user.id)
        .order_by(models.Income.date)
        .all()
    )


@router.post("/income", response_model=IncomeOut, status_code=201)
def create_income(
    payload: IncomeCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = models.Income(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/income/{income_id}", response_model=IncomeOut)
def update_income(
    income_id: int,
    payload: IncomeUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = _get_owned_or_404(db, income_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/income/{income_id}", status_code=204)
def delete_income(
    income_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = _get_owned_or_404(db, income_id, user.id)
    db.delete(row)
    db.commit()


@router.get("/income/summary")
def income_summary(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return income_logic.summary(fetch_income(db, user.id))
