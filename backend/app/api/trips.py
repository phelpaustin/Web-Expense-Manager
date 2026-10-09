import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, is_group_member, require_role_at_least
from app.api.groups import cascade_delete_group
from app.api.options import default_currency_for
from app.core import fx
from app.core.fx import normalize_convertible_currency
from app.db.database import get_db
from app.core.money import MAX_MONEY
from app.core.validation import PartialUpdate
from app.db import models
from app.logic import currency as currency_logic
from app.logic import trips as trips_logic

router = APIRouter()

STATUSES = ["Planned", "Active", "Completed"]


class TripCreate(BaseModel):
    name: str = Field(min_length=1)
    destination: str = ""
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)
    # Reporting currency of the trip; None = the creator's base currency.
    currency: str | None = None
    status: str = "Planned"
    parent_group_id: int | None = None

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None


class TripUpdate(PartialUpdate):
    # destination, dates, budget and parent_group_id may be null (clear them).
    not_nullable = frozenset({"name", "currency", "status"})
    name: str | None = Field(default=None, min_length=1)
    destination: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)
    currency: str | None = None
    status: str | None = None
    parent_group_id: int | None = None

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None


def _trip_or_404(db: Session, trip_id: int) -> models.Group:
    trip = db.get(models.Group, trip_id)
    if trip is None or trip.space_type != "trip":
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _member_or_403(db: Session, trip_id: int, user_id: int) -> models.GroupMember:
    member = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == trip_id, models.GroupMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this trip")
    return member


def _require_trip_owner(db: Session, trip_id: int, user_id: int) -> models.GroupMember:
    member = _member_or_403(db, trip_id, user_id)
    if member.role != "owner":
        raise HTTPException(status_code=403, detail="Only the trip owner can do this")
    return member


def _require_trip_manage(db: Session, trip_id: int, user_id: int) -> models.GroupMember:
    return require_role_at_least(db, trip_id, user_id, "admin", "Only the trip owner or an admin can do this")


def _validate_parent(db: Session, user_id: int, parent_group_id: int | None) -> None:
    if parent_group_id is None:
        return
    parent = db.get(models.Group, parent_group_id)
    if parent is None or parent.space_type == "trip" or not is_group_member(db, parent_group_id, user_id):
        raise HTTPException(status_code=400, detail="Invalid parent Expense Space")


def _convert_trip_expenses(expenses: list[dict], currency: str) -> tuple[list[dict], list[dict]]:
    """Convert trip expenses into the trip currency at each expense's date.

    Returns (converted, unconvertible): expenses whose currency has no exchange
    rate are returned separately, not raised on, so the caller can say exactly
    which ones are the problem.
    """
    currency = currency or "SEK"
    fx.ensure_rates_for(expenses, currency)
    try:
        ok, bad = currency_logic.partition_convertible(expenses, currency, fx.get_rate)
        return currency_logic.convert_expenses(ok, currency, fx.get_rate), bad
    except currency_logic.CurrencyConversionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _describe_unconverted(rows: list[dict]) -> list[dict]:
    return [
        {
            "id": r.get("id"),
            "date": r["date"].isoformat() if hasattr(r.get("date"), "isoformat") else r.get("date"),
            "description": r.get("description") or "",
            "amount": r["amount"],
            "currency": r.get("currency"),
        }
        for r in rows
    ]


def _serialize_trip(db: Session, trip: models.Group, member: models.GroupMember) -> dict:
    member_count = db.query(models.GroupMember).filter(models.GroupMember.group_id == trip.id).count()
    return {
        "id": trip.id,
        "name": member.local_name or trip.name,
        "destination": trip.destination or "",
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "budget": trip.budget,
        "currency": trip.currency or "SEK",
        "status": trip.status or "Planned",
        "parent_group_id": trip.parent_group_id,
        "local_name": member.local_name,
        "local_parent_group_id": member.local_parent_group_id,
        "role": member.role,
        "member_count": member_count,
    }


@router.get("/trips")
def list_trips(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    memberships = db.query(models.GroupMember).filter(models.GroupMember.user_id == user.id).all()
    trips = []
    for m in memberships:
        trip = db.get(models.Group, m.group_id)
        if trip and trip.space_type == "trip":
            trips.append(_serialize_trip(db, trip, m))
    trips.sort(key=lambda t: (t["start_date"] is None, t["start_date"] or datetime.date.min), reverse=True)
    return trips


@router.post("/trips", status_code=201)
def create_trip(
    payload: TripCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    status = payload.status if payload.status in STATUSES else "Planned"
    _validate_parent(db, user.id, payload.parent_group_id)
    trip = models.Group(
        owner_id=user.id,
        name=payload.name.strip(),
        space_type="trip",
        parent_group_id=payload.parent_group_id,
        destination=payload.destination,
        start_date=payload.start_date,
        end_date=payload.end_date,
        budget=payload.budget,
        currency=payload.currency or default_currency_for(db, user.id),
        status=status,
    )
    db.add(trip)
    db.flush()
    member = models.GroupMember(group_id=trip.id, user_id=user.id, role="owner")
    db.add(member)
    db.commit()
    db.refresh(trip)
    return _serialize_trip(db, trip, member)


@router.put("/trips/{trip_id}")
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    trip = _trip_or_404(db, trip_id)
    member = _require_trip_manage(db, trip_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_group_id" in data:
        _validate_parent(db, user.id, data["parent_group_id"])
    for field, value in data.items():
        if field == "status" and value not in STATUSES:
            continue
        setattr(trip, field, value)
    db.commit()
    db.refresh(trip)
    return _serialize_trip(db, trip, member)


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    trip = _trip_or_404(db, trip_id)
    _require_trip_owner(db, trip_id, user.id)
    cascade_delete_group(db, trip)
    db.commit()


@router.get("/trips/{trip_id}/summary")
def trip_summary(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    trip = _trip_or_404(db, trip_id)
    _member_or_403(db, trip_id, user.id)
    expenses = db.query(models.Expense).filter(models.Expense.group_id == trip.id).all()
    expense_dicts, unconverted = _convert_trip_expenses(
        [{"date": e.date, "category": e.category, "amount": e.amount, "currency": e.currency} for e in expenses],
        trip.currency or "SEK",
    )
    trip_dict = {"id": trip.id, "budget": trip.budget, "currency": trip.currency or "SEK"}
    summary = trips_logic.trip_summary(trip_dict, expense_dicts)
    # Expenses with no exchange rate are left out of the totals (and counted) instead of failing.
    summary["unconverted_count"] = len(unconverted)
    return summary


@router.get("/trips/{trip_id}/expenses")
def trip_expenses(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _trip_or_404(db, trip_id)
    _member_or_403(db, trip_id, user.id)
    rows = (
        db.query(models.Expense)
        .filter(models.Expense.group_id == trip_id)
        .order_by(models.Expense.date.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "date": r.date.isoformat(),
            "category": r.category,
            "description": r.description,
            "shop": r.shop,
            "amount": r.amount,
            "currency": r.currency,
        }
        for r in rows
    ]


@router.get("/trips/{trip_id}/settlement")
def trip_settlement(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Who paid what vs. an equal split, and the minimal set of payments to settle up."""
    trip = _trip_or_404(db, trip_id)
    _member_or_403(db, trip_id, user.id)

    member_rows = db.query(models.GroupMember).filter(models.GroupMember.group_id == trip_id).all()
    members = []
    for m in member_rows:
        u = db.get(models.User, m.user_id)
        members.append({"user_id": m.user_id, "name": u.name if u else "", "email": u.email if u else ""})

    expenses = (
        db.query(
            models.Expense.id,
            models.Expense.user_id,
            models.Expense.date,
            models.Expense.description,
            models.Expense.amount,
            models.Expense.currency,
        )
        .filter(models.Expense.group_id == trip_id)
        .all()
    )
    currency = trip.currency or "SEK"
    expense_dicts, unconverted = _convert_trip_expenses(
        [
            {
                "id": e.id,
                "user_id": e.user_id,
                "date": e.date,
                "description": e.description,
                "amount": e.amount,
                "currency": e.currency,
            }
            for e in expenses
        ],
        currency,
    )

    if unconverted:
        # Settlement must be exact, so don't guess: leaving these out would give a
        # wrong "who owes whom". Say which expenses need fixing instead of erroring.
        return {
            "complete": False,
            "currency": currency,
            "message": (
                f"{len(unconverted)} expense(s) in a currency without an exchange rate can't be included. "
                "Change their currency to settle up."
            ),
            "unconverted_expenses": _describe_unconverted(unconverted),
            "total_spent": 0,
            "share_per_person": 0,
            "per_member": [],
            "transactions": [],
        }
    settlement = trips_logic.trip_settlement(members, expense_dicts, currency)
    settlement["complete"] = True
    return settlement
