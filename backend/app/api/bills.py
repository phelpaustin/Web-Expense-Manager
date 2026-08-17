import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.expenses import fetch_expenses
from app.db.database import get_db
from app.db import models
from app.logic import bills as bills_logic

router = APIRouter()


# ── Pending bills ─────────────────────────────────────────────
class PendingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    shop: str
    amount: float
    note: str
    status: str


class PendingCreate(BaseModel):
    date: datetime.date
    shop: str = Field(min_length=1)
    amount: float = Field(gt=0)
    note: str = ""


def _pending_or_404(db: Session, bill_id: int, user_id: int) -> models.PendingBill:
    b = db.get(models.PendingBill, bill_id)
    if b is None or b.user_id != user_id:
        raise HTTPException(status_code=404, detail="Pending bill not found")
    return b


@router.get("/pending-bills", response_model=list[PendingOut])
def list_pending(
    include_itemised: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.PendingBill).filter(models.PendingBill.user_id == user.id)
    if not include_itemised:
        q = q.filter(models.PendingBill.status == "pending")
    return q.order_by(models.PendingBill.date.desc()).all()


@router.post("/pending-bills", response_model=PendingOut, status_code=201)
def create_pending(
    payload: PendingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    b = models.PendingBill(user_id=user.id, **payload.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/pending-bills/{bill_id}", status_code=204)
def delete_pending(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db.delete(_pending_or_404(db, bill_id, user.id))
    db.commit()


@router.post("/pending-bills/{bill_id}/itemise")
def itemise_pending(
    bill_id: int,
    category: str = "Bills",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Convert a pending bill into a real expense and archive it as itemised."""
    b = _pending_or_404(db, bill_id, user.id)
    db.add(
        models.Expense(
            user_id=user.id,
            date=b.date,
            category=category or "Bills",
            description=b.shop,
            amount=b.amount,
        )
    )
    b.status = "itemised"
    db.commit()
    return {"itemised": bill_id, "expense_created": True}


# ── Manual bills ──────────────────────────────────────────────
class ManualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    shop: str
    amount: float
    note: str


class ManualCreate(BaseModel):
    date: datetime.date
    shop: str = Field(min_length=1)
    amount: float = Field(gt=0)
    note: str = ""


@router.get("/bills-ledger/manual", response_model=list[ManualOut])
def list_manual(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.ManualBill)
        .filter(models.ManualBill.user_id == user.id)
        .order_by(models.ManualBill.date.desc())
        .all()
    )


@router.post("/bills-ledger/manual", response_model=ManualOut, status_code=201)
def create_manual(
    payload: ManualCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    m = models.ManualBill(user_id=user.id, **payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/bills-ledger/manual/{manual_id}", status_code=204)
def delete_manual(
    manual_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    m = db.get(models.ManualBill, manual_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status_code=404, detail="Manual bill not found")
    db.delete(m)
    db.commit()


# ── Consolidated ledger ───────────────────────────────────────
@router.get("/bills-ledger")
def get_ledger(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id)
    pending = [
        {"id": b.id, "date": b.date, "shop": b.shop, "amount": b.amount}
        for b in db.query(models.PendingBill)
        .filter(models.PendingBill.user_id == user.id, models.PendingBill.status == "pending")
        .all()
    ]
    manual = [
        {"id": m.id, "date": m.date, "shop": m.shop, "amount": m.amount}
        for m in db.query(models.ManualBill).filter(models.ManualBill.user_id == user.id).all()
    ]
    return bills_logic.build_ledger(expenses, pending, manual)
