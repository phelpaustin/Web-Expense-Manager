import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.logic import recurring as rec

router = APIRouter()

FREQUENCIES = list(rec.FREQUENCIES.keys())


class RecurringCreate(BaseModel):
    item: str = Field(min_length=1)
    category: str = ""
    amount: float = Field(gt=0)
    frequency: str = "Monthly"
    note: str = ""
    auto_post: bool = False

    @field_validator("frequency")
    @classmethod
    def _valid_frequency(cls, v: str) -> str:
        if v not in rec.FREQUENCIES:
            raise ValueError(f"frequency must be one of {FREQUENCIES}")
        return v


class RecurringBackfill(BaseModel):
    start_date: datetime.date
    end_date: datetime.date | None = None
    amount: float | None = Field(default=None, gt=0)


class RecurringUpdate(BaseModel):
    item: str | None = Field(default=None, min_length=1)
    category: str | None = None
    amount: float | None = Field(default=None, gt=0)
    frequency: str | None = None
    note: str | None = None
    auto_post: bool | None = None

    @field_validator("frequency")
    @classmethod
    def _valid_frequency(cls, v: str | None) -> str | None:
        if v is not None and v not in rec.FREQUENCIES:
            raise ValueError(f"frequency must be one of {FREQUENCIES}")
        return v


def _serialize(t: models.RecurringTemplate, today: datetime.date) -> dict:
    return {
        "id": t.id,
        "item": t.item,
        "category": t.category,
        "amount": t.amount,
        "frequency": t.frequency,
        "note": t.note,
        "auto_post": t.auto_post,
        "last_applied": t.last_applied.isoformat() if t.last_applied else None,
        "due": rec.is_due(t.last_applied, t.frequency, today),
    }


def _get_owned_or_404(db: Session, template_id: int, user_id: int) -> models.RecurringTemplate:
    t = db.get(models.RecurringTemplate, template_id)
    if t is None or t.user_id != user_id:
        raise HTTPException(status_code=404, detail="Recurring template not found")
    return t


def _post_expense(db: Session, user_id: int, template: models.RecurringTemplate, when: datetime.date):
    db.add(
        models.Expense(
            user_id=user_id,
            date=when,
            category=template.category or "Recurring",
            description=template.item,
            amount=template.amount,
        )
    )


@router.get("/recurring")
def list_recurring(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    today = datetime.date.today()
    rows = (
        db.query(models.RecurringTemplate)
        .filter(models.RecurringTemplate.user_id == user.id)
        .order_by(models.RecurringTemplate.item)
        .all()
    )
    return [_serialize(t, today) for t in rows]


@router.post("/recurring", status_code=201)
def create_recurring(
    payload: RecurringCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    t = models.RecurringTemplate(user_id=user.id, **payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return _serialize(t, datetime.date.today())


@router.put("/recurring/{template_id}")
def update_recurring(
    template_id: int,
    payload: RecurringUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    t = _get_owned_or_404(db, template_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    return _serialize(t, datetime.date.today())


@router.delete("/recurring/{template_id}", status_code=204)
def delete_recurring(
    template_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    t = _get_owned_or_404(db, template_id, user.id)
    db.delete(t)
    db.commit()


@router.post("/recurring/{template_id}/apply")
def apply_recurring(
    template_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Apply one template once, dated today, and advance last_applied."""
    today = datetime.date.today()
    t = _get_owned_or_404(db, template_id, user.id)
    _post_expense(db, user.id, t, today)
    t.last_applied = today
    db.commit()
    return {"applied": 1, "item": t.item}


@router.post("/recurring/{template_id}/backfill")
def backfill_recurring(
    template_id: int,
    payload: RecurringBackfill,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Post historical expenses for a template that existed before it was
    tracked (e.g. rent paid monthly for the past year). Pass ``amount`` to
    use a different rate than the template's current amount for this
    stretch — call again with a later ``start_date`` and the new amount to
    record a mid-history rate change (e.g. a rent increase).
    """
    today = datetime.date.today()
    t = _get_owned_or_404(db, template_id, user.id)
    end = min(payload.end_date or today, today)
    if payload.start_date > end:
        raise HTTPException(status_code=400, detail="start_date must not be after end_date")
    dates = rec.backfill_dates(payload.start_date, end, t.frequency)
    if not dates:
        return {"applied": 0, "item": t.item}
    amount = payload.amount if payload.amount is not None else t.amount
    for when in dates:
        db.add(
            models.Expense(
                user_id=user.id,
                date=when,
                category=t.category or "Recurring",
                description=t.item,
                amount=amount,
            )
        )
    if t.last_applied is None or dates[-1] > t.last_applied:
        t.last_applied = dates[-1]
    db.commit()
    return {"applied": len(dates), "item": t.item, "dates": [d.isoformat() for d in dates]}


@router.post("/recurring/apply-due")
def apply_due_recurring(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Catch-up: post one expense per missed period for every due template."""
    today = datetime.date.today()
    templates = (
        db.query(models.RecurringTemplate)
        .filter(models.RecurringTemplate.user_id == user.id)
        .all()
    )
    applied: list[str] = []
    for t in templates:
        dates = rec.due_dates(t.last_applied, t.frequency, today)
        if not dates:
            continue
        for when in dates:
            _post_expense(db, user.id, t, when)
            applied.append(t.item)
        t.last_applied = today
    db.commit()
    return {"applied": len(applied), "items": applied}
