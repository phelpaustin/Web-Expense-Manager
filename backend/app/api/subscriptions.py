"""Subscription finder: repeating charges the user has not set up as recurring payments."""
import datetime as dt
from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import convert_rows, get_reporting_currency
from app.core.money import quantize_money
from app.core.validation import Name
from app.db import models
from app.db.database import get_db
from app.logic import subscriptions as logic
from app.logic.names import clean_name, name_key

router = APIRouter()

LOOKBACK_DAYS = 730


class NameIn(BaseModel):
    name: Name


def _single_purchases(db: Session, user_id: int, since: dt.date) -> list[dict]:
    """Personal expenses that stand alone: not an item of a bill with several items."""
    sizes = dict(
        db.query(models.Expense.source_bill_id, func.count(models.Expense.id))
        .filter(models.Expense.user_id == user_id, models.Expense.source_bill_id.isnot(None))
        .group_by(models.Expense.source_bill_id)
        .all()
    )
    rows = (
        db.query(models.Expense)
        .filter(models.Expense.user_id == user_id, models.Expense.group_id.is_(None), models.Expense.date >= since)
        .all()
    )
    return [
        {
            "id": e.id, "date": e.date, "amount": e.amount, "currency": e.currency, "shop": e.shop,
            "description": e.description, "category": e.category, "tracked": e.recurring_template_id is not None,
        }
        for e in rows
        if e.source_bill_id is None or sizes.get(e.source_bill_id, 1) <= 1
    ]


@router.get("/subscriptions")
def find_subscriptions(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Repeating charges found in the expenses, what they cost per month and year, price rises, and
    the ones that seem to have stopped. Names the user set up as recurring, or marked as not a
    subscription, are not listed."""
    today = dt.date.today()
    templates = db.query(models.RecurringTemplate.item).filter(models.RecurringTemplate.user_id == user.id).all()
    ignored = db.query(models.IgnoredSubscription).filter(models.IgnoredSubscription.user_id == user.id).all()
    found = logic.find_subscriptions(
        _single_purchases(db, user.id, today - dt.timedelta(days=LOOKBACK_DAYS)),
        {name_key(t.item) for t in templates},
        {i.key for i in ignored},
        today,
    )
    items = found["items"]

    # Totals in the reporting currency, one conversion row per item and per period.
    rows = []
    for n, i in enumerate(items):
        rows.append({"ref": f"m{n}", "date": today, "amount": i["monthly_native"], "currency": i["currency"]})
        rows.append({"ref": f"y{n}", "date": today, "amount": i["yearly_native"], "currency": i["currency"]})
    converted, unconverted = convert_rows(db, user.id, rows)
    by_ref = {r["ref"]: r["amount"] for r in converted}
    zero = quantize_money(0)
    for n, i in enumerate(items):
        i["monthly"], i["yearly"] = by_ref.get(f"m{n}"), by_ref.get(f"y{n}")
    return {
        "currency": get_reporting_currency(db, user.id),
        "count": len(items),
        "monthly_total": sum((i["monthly"] for i in items if i["monthly"] is not None), zero),
        "yearly_total": sum((i["yearly"] for i in items if i["yearly"] is not None), zero),
        "unconverted_count": unconverted // 2,
        "items": items,
        "stopped": found["stopped"],
        "tracked_count": found["tracked_count"],
        "ignored": sorted(({"key": i.key, "name": i.name} for i in ignored), key=lambda x: x["name"].lower()),
    }


@router.post("/subscriptions/ignore", status_code=204)
def ignore_subscription(
    payload: NameIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    """Say a name is not a subscription: the finder stops listing it."""
    key = name_key(payload.name)
    if key and not (
        db.query(models.IgnoredSubscription.id)
        .filter(models.IgnoredSubscription.user_id == user.id, models.IgnoredSubscription.key == key)
        .first()
    ):
        db.add(models.IgnoredSubscription(user_id=user.id, key=key, name=clean_name(payload.name)))
        db.commit()


@router.post("/subscriptions/unignore", status_code=204)
def unignore_subscription(
    payload: NameIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    db.query(models.IgnoredSubscription).filter(
        models.IgnoredSubscription.user_id == user.id, models.IgnoredSubscription.key == name_key(payload.name)
    ).delete(synchronize_session=False)
    db.commit()
