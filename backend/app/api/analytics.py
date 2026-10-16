from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.api.aliases import load_alias_maps
from app.api.expenses import fetch_expenses_in_reporting_currency, fetch_expenses_in_reporting_currency_ex
from app.api.options import get_reporting_currency
from app.logic import analytics as analytics_logic
from app.logic import category_change as category_change_logic
from app.logic import names, price_tracker

router = APIRouter()


@router.get("/analytics/trends")
def analytics_trends(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses_in_reporting_currency(db, user.id, scope, space_ids)
    monthly = analytics_logic.monthly_totals(expenses)
    return {
        "monthly": monthly,
        "change": analytics_logic.month_over_month_change(monthly),
        "forecast_next_month": analytics_logic.forecast_next_month(monthly),
        "forecast_available": analytics_logic.HAS_STATS,
        # Month still in progress: excluded from change/forecast above.
        "current_month": analytics_logic.current_month_key(),
    }


@router.get("/analytics/categories")
def analytics_categories(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return analytics_logic.category_breakdown(fetch_expenses_in_reporting_currency(db, user.id, scope, space_ids))


@router.get("/analytics/category-change")
def analytics_category_change(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    top: int = Query(default=category_change_logic.DEFAULT_TOP, ge=1, le=50),
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Which categories explain the change in spending versus the month before.

    `month` is YYYY-MM; by default the last finished month (the pair behind the
    dashboard's "vs previous month" figure). The month in progress is compared like for
    like: its days so far against the same days of the month before.
    """
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    chosen = month or category_change_logic.default_month(expenses)
    result = category_change_logic.category_change(expenses, chosen, top=top)
    result["currency"] = get_reporting_currency(db, user.id)
    # Expenses left out because their currency has no exchange rate (same as the other totals).
    result["unconverted_count"] = unconverted
    return result


def _price_rows(db: Session, user: models.User) -> tuple[list[dict], dict[str, str]]:
    """The user's expenses with their saved item/shop merges applied, plus the item
    aliases (so a request naming an old spelling still finds its merged item)."""
    item_aliases, shop_aliases = load_alias_maps(db, user.id)
    rows = names.canonicalise(fetch_expenses_in_reporting_currency(db, user.id), item_aliases, shop_aliases)
    return rows, item_aliases


@router.get("/analytics/price-trends")
def analytics_price_trends(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return price_tracker.price_trends(_price_rows(db, user)[0])


@router.get("/analytics/price-trends/shops")
def analytics_price_shop_comparison(
    item: str,
    unit: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    shop: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows, item_aliases = _price_rows(db, user)
    return price_tracker.shop_comparison(rows, names.resolve_name(item, item_aliases), unit, category, brand, shop)


@router.get("/analytics/price-trends/history")
def analytics_price_history(
    item: str,
    unit: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    shop: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows, item_aliases = _price_rows(db, user)
    return price_tracker.price_history(rows, names.resolve_name(item, item_aliases), unit, category, brand, shop)


@router.get("/analytics/price-trends/detail")
def analytics_price_detail(
    item: str,
    unit: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    shop: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """One item's comparison, optionally narrowed to a brand and to the shops to include.

    Leave `brand` out for every brand (`brand=` alone means "no brand recorded") and
    leave `shop` out for every shop (repeat it to include only those shops).
    """
    rows, item_aliases = _price_rows(db, user)
    return price_tracker.price_detail(rows, names.resolve_name(item, item_aliases), unit, category, brand, shop)
