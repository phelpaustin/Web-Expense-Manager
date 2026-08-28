from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.api.expenses import fetch_expenses
from app.logic import analytics as analytics_logic
from app.logic import price_tracker

router = APIRouter()


@router.get("/analytics/trends")
def analytics_trends(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id)
    monthly = analytics_logic.monthly_totals(expenses)
    return {
        "monthly": monthly,
        "change": analytics_logic.month_over_month_change(monthly),
        "forecast_next_month": analytics_logic.forecast_next_month(monthly),
        "forecast_available": analytics_logic.HAS_STATS,
    }


@router.get("/analytics/categories")
def analytics_categories(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return analytics_logic.category_breakdown(fetch_expenses(db, user.id))


@router.get("/analytics/price-trends")
def analytics_price_trends(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return price_tracker.price_trends(fetch_expenses(db, user.id))


@router.get("/analytics/price-trends/shops")
def analytics_price_shop_comparison(
    item: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return price_tracker.shop_comparison(fetch_expenses(db, user.id), item)


@router.get("/analytics/price-trends/history")
def analytics_price_history(
    item: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return price_tracker.price_history(fetch_expenses(db, user.id), item)
