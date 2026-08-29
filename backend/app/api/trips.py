import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, is_group_member
from app.api.groups import cascade_delete_group
from app.db.database import get_db
from app.db import models
from app.logic import trips as trips_logic

router = APIRouter()

STATUSES = ["Planned", "Active", "Completed"]


class TripCreate(BaseModel):
    name: str = Field(min_length=1)
    destination: str = ""
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget: float | None = Field(default=None, gt=0)
    currency: str = "SEK"
    status: str = "Planned"
    parent_group_id: int | None = None


class TripUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    destination: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget: float | None = Field(default=None, gt=0)
    currency: str | None = None
    status: str | None = None
    parent_group_id: int | None = None


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


def _validate_parent(db: Session, user_id: int, parent_group_id: int | None) -> None:
    if parent_group_id is None:
        return
    parent = db.get(models.Group, parent_group_id)
    if parent is None or parent.space_type == "trip" or not is_group_member(db, parent_group_id, user_id):
        raise HTTPException(status_code=400, detail="Invalid parent Expense Space")


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
        currency=payload.currency or "SEK",
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
    member = _require_trip_owner(db, trip_id, user.id)
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
    expense_dicts = [{"category": e.category, "amount": e.amount} for e in expenses]
    trip_dict = {"id": trip.id, "budget": trip.budget}
    return trips_logic.trip_summary(trip_dict, expense_dicts)


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
