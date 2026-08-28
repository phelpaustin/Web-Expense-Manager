import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.logic import trips as trips_logic

router = APIRouter()

STATUSES = ["Planned", "Active", "Completed"]


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    destination: str
    start_date: datetime.date | None
    end_date: datetime.date | None
    budget: float | None
    currency: str
    status: str


class TripCreate(BaseModel):
    name: str = Field(min_length=1)
    destination: str = ""
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget: float | None = Field(default=None, gt=0)
    currency: str = "SEK"
    status: str = "Planned"


class TripUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    destination: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget: float | None = Field(default=None, gt=0)
    currency: str | None = None
    status: str | None = None


def _trip_or_404(db: Session, trip_id: int, user_id: int) -> models.Trip:
    trip = db.get(models.Trip, trip_id)
    if trip is None or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("/trips", response_model=list[TripOut])
def list_trips(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Trip)
        .filter(models.Trip.user_id == user.id)
        .order_by(models.Trip.start_date.desc().nullslast(), models.Trip.id.desc())
        .all()
    )


@router.post("/trips", response_model=TripOut, status_code=201)
def create_trip(
    payload: TripCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    if data["status"] not in STATUSES:
        data["status"] = "Planned"
    trip = models.Trip(user_id=user.id, **data)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.put("/trips/{trip_id}", response_model=TripOut)
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    trip = _trip_or_404(db, trip_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "status" and value not in STATUSES:
            continue
        setattr(trip, field, value)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    trip = _trip_or_404(db, trip_id, user.id)
    db.query(models.Expense).filter(models.Expense.trip_id == trip.id).update({"trip_id": None})
    db.delete(trip)
    db.commit()


@router.get("/trips/{trip_id}/summary")
def trip_summary(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    trip = _trip_or_404(db, trip_id, user.id)
    expenses = (
        db.query(models.Expense)
        .filter(models.Expense.trip_id == trip.id, models.Expense.user_id == user.id)
        .all()
    )
    expense_dicts = [{"category": e.category, "amount": e.amount} for e in expenses]
    trip_dict = {"id": trip.id, "budget": trip.budget}
    return trips_logic.trip_summary(trip_dict, expense_dicts)


@router.get("/trips/{trip_id}/expenses")
def trip_expenses(
    trip_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _trip_or_404(db, trip_id, user.id)
    rows = (
        db.query(models.Expense)
        .filter(models.Expense.trip_id == trip_id, models.Expense.user_id == user.id)
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
