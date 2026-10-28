"""Savings goals: a target (optionally by a date) and the deposits and withdrawals made towards it.

Goals are personal and in their own currency. How far along each is, and what it needs per month,
comes from `app.logic.savings_goals`.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import default_currency_for
from app.core.fx import normalize_convertible_currency
from app.core.money import MAX_MONEY, quantize_money
from app.core.validation import PartialUpdate, Text
from app.db import models
from app.db.database import get_db
from app.logic import savings_goals as goals_logic

router = APIRouter()

MAX_GOALS = 50
MAX_CONTRIBUTIONS = 2000           # per goal
MAX_NAME = 120                     # the column's width
GoalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME)]
# The server's date can be a day behind someone just ahead of it (Stockholm just after midnight).
FUTURE_SLACK = datetime.timedelta(days=1)


def _valid_currency(value: str | None) -> str | None:
    return normalize_convertible_currency(value) if value is not None else None


def _money(value: Decimal) -> Decimal:
    return quantize_money(value)


class GoalCreate(BaseModel):
    name: GoalName
    target_amount: Decimal = Field(gt=0, le=MAX_MONEY)
    currency: str | None = None            # None = the user's base currency
    target_date: datetime.date | None = None
    note: Text = ""

    check_currency = field_validator("currency")(lambda cls, v: _valid_currency(v))
    check_amount = field_validator("target_amount")(lambda cls, v: _positive(v))


class GoalUpdate(PartialUpdate):
    not_nullable = frozenset({"name", "target_amount", "currency", "note"})
    name: GoalName | None = None
    target_amount: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)
    currency: str | None = None
    target_date: datetime.date | None = None     # null removes the date
    note: Text | None = None

    check_currency = field_validator("currency")(lambda cls, v: _valid_currency(v))
    check_amount = field_validator("target_amount")(lambda cls, v: None if v is None else _positive(v))


def _positive(value: Decimal) -> Decimal:
    rounded = _money(value)
    if rounded <= 0:
        raise ValueError("must be at least 0.01")
    return rounded


class ContributionCreate(BaseModel):
    date: datetime.date | None = None      # None = today
    amount: Decimal = Field(le=MAX_MONEY, ge=-MAX_MONEY)   # negative takes money back out
    note: Text = ""

    @field_validator("amount")
    @classmethod
    def _not_zero(cls, v: Decimal) -> Decimal:
        rounded = _money(v)
        if rounded == 0:
            raise ValueError("must not be zero")
        return rounded


def _contribution_dict(c) -> dict:
    return {"id": c.id, "date": c.date, "amount": c.amount, "note": c.note}


def _goal_dict(goal: models.SavingsGoal, contributions: list[dict], today: datetime.date) -> dict:
    return {
        "id": goal.id,
        "name": goal.name,
        "note": goal.note,
        "currency": goal.currency,
        "target_amount": goal.target_amount,
        "target_date": goal.target_date,
        **goals_logic.goal_progress(
            {"target_amount": goal.target_amount, "target_date": goal.target_date}, contributions, today
        ),
    }


def _get_goal_or_404(db: Session, goal_id: int, user_id: int) -> models.SavingsGoal:
    goal = db.get(models.SavingsGoal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    return goal


def _contributions_of(db: Session, goal_id: int) -> list[models.SavingsContribution]:
    return (
        db.query(models.SavingsContribution)
        .filter(models.SavingsContribution.goal_id == goal_id)
        .order_by(models.SavingsContribution.date.desc(), models.SavingsContribution.id.desc())
        .all()
    )


def _saved(db: Session, goal_id: int) -> Decimal:
    rows = db.query(models.SavingsContribution.amount).filter(models.SavingsContribution.goal_id == goal_id).all()
    return sum((r[0] for r in rows), Decimal(0))


def _detail(db: Session, goal: models.SavingsGoal) -> dict:
    rows = _contributions_of(db, goal.id)
    contributions = [_contribution_dict(c) for c in rows]
    return {**_goal_dict(goal, contributions, datetime.date.today()), "contributions": contributions}


@router.get("/savings-goals")
def list_goals(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Every goal with its progress, unfinished ones first (nearest target date first)."""
    today = datetime.date.today()
    goals = db.query(models.SavingsGoal).filter(models.SavingsGoal.user_id == user.id).all()
    by_goal: dict[int, list[dict]] = {g.id: [] for g in goals}
    if goals:
        rows = (
            db.query(models.SavingsContribution.goal_id, models.SavingsContribution.date, models.SavingsContribution.amount)
            .filter(models.SavingsContribution.user_id == user.id)
            .all()
        )
        for goal_id, day, amount in rows:
            if goal_id in by_goal:
                by_goal[goal_id].append({"date": day, "amount": amount})
    items = goals_logic.sort_goals([_goal_dict(g, by_goal[g.id], today) for g in goals])
    return {"goals": items, "summary": goals_logic.summary(items), "limit": MAX_GOALS}


@router.post("/savings-goals", status_code=201)
def create_goal(
    payload: GoalCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if db.query(models.SavingsGoal).filter(models.SavingsGoal.user_id == user.id).count() >= MAX_GOALS:
        raise HTTPException(status_code=400, detail=f"You can have up to {MAX_GOALS} savings goals")
    data = payload.model_dump()
    data["currency"] = data["currency"] or default_currency_for(db, user.id)
    goal = models.SavingsGoal(user_id=user.id, **data)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _detail(db, goal)


@router.get("/savings-goals/{goal_id}")
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return _detail(db, _get_goal_or_404(db, goal_id, user.id))


@router.put("/savings-goals/{goal_id}")
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    goal = _get_goal_or_404(db, goal_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "currency" in changes and changes["currency"] != goal.currency:
        # The saved amounts are in the old currency; relabelling them would change what they are worth.
        has_any = db.query(models.SavingsContribution.id).filter(models.SavingsContribution.goal_id == goal.id).first()
        if has_any:
            raise HTTPException(status_code=400, detail="The currency can't be changed once money has been added to the goal")
    for field, value in changes.items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return _detail(db, goal)


@router.delete("/savings-goals/{goal_id}", status_code=204)
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    goal = _get_goal_or_404(db, goal_id, user.id)
    db.query(models.SavingsContribution).filter(models.SavingsContribution.goal_id == goal.id).delete(synchronize_session=False)
    db.delete(goal)
    db.commit()


@router.post("/savings-goals/{goal_id}/contributions", status_code=201)
def add_contribution(
    goal_id: int,
    payload: ContributionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Put money towards the goal, or take some back out with a negative amount."""
    goal = _get_goal_or_404(db, goal_id, user.id)
    today = datetime.date.today()
    day = payload.date or today
    if day > today + FUTURE_SLACK:
        raise HTTPException(status_code=422, detail="The date can't be in the future")
    count = db.query(models.SavingsContribution).filter(models.SavingsContribution.goal_id == goal.id).count()
    if count >= MAX_CONTRIBUTIONS:
        raise HTTPException(status_code=400, detail=f"A goal can hold up to {MAX_CONTRIBUTIONS} deposits and withdrawals")
    if _saved(db, goal.id) + payload.amount < 0:
        raise HTTPException(status_code=400, detail="That would take out more than has been saved")
    db.add(models.SavingsContribution(goal_id=goal.id, user_id=user.id, date=day, amount=payload.amount, note=payload.note))
    db.commit()
    return _detail(db, goal)


@router.delete("/savings-goals/{goal_id}/contributions/{contribution_id}")
def delete_contribution(
    goal_id: int,
    contribution_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    goal = _get_goal_or_404(db, goal_id, user.id)
    row = db.get(models.SavingsContribution, contribution_id)
    if row is None or row.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="Deposit or withdrawal not found")
    if _saved(db, goal.id) - row.amount < 0:
        raise HTTPException(status_code=400, detail="Removing this deposit would leave less than nothing saved; remove the withdrawals made after it first")
    db.delete(row)
    db.commit()
    return _detail(db, goal)
