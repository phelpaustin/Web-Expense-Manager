import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import convert_rows, default_currency_for
from app.core.fx import normalize_convertible_currency
from app.db.database import get_db
from app.core.validation import PartialUpdate
from app.core.money import MAX_MONEY
from app.db import models
from app.logic import income as income_logic

router = APIRouter()


class IncomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    amount: Decimal
    source: str
    note: str
    currency: str


def _valid_currency(value: str | None) -> str | None:
    return normalize_convertible_currency(value) if value is not None else None


class IncomeCreate(BaseModel):
    date: datetime.date
    amount: Decimal = Field(gt=0, le=MAX_MONEY)
    source: str = Field(min_length=1)
    note: str = ""
    currency: str | None = None  # None = the user's base currency

    check_currency = field_validator("currency")(lambda cls, v: _valid_currency(v))


class IncomeUpdate(PartialUpdate):
    not_nullable = frozenset({"date", "amount", "source", "note", "currency"})
    date: datetime.date | None = None
    amount: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)
    source: str | None = Field(default=None, min_length=1)
    note: str | None = None
    currency: str | None = None

    check_currency = field_validator("currency")(lambda cls, v: _valid_currency(v))


def fetch_income(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(models.Income)
        .filter(models.Income.user_id == user_id)
        .order_by(models.Income.date)
        .all()
    )
    return [
        {"id": r.id, "date": r.date, "amount": r.amount, "source": r.source, "note": r.note, "currency": r.currency}
        for r in rows
    ]


def fetch_income_in_reporting_currency(db: Session, user_id: int) -> list[dict]:
    """Income rows converted into the user's base currency at each row's date."""
    return convert_rows(db, user_id, fetch_income(db, user_id))[0]


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
    data = payload.model_dump()
    data["currency"] = data["currency"] or default_currency_for(db, user.id)
    row = models.Income(user_id=user.id, **data)
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
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
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
    return income_logic.summary(fetch_income_in_reporting_currency(db, user.id))
