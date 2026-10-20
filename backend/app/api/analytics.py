from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.api.aliases import load_alias_maps
from app.api.expenses import fetch_expenses, fetch_expenses_in_reporting_currency, fetch_expenses_in_reporting_currency_ex
from app.api.options import convert_rows, get_reporting_currency
from app.logic import analytics as analytics_logic
from app.logic import category_change as category_change_logic
from app.logic import spending_mix as spending_mix_logic
from app.logic import shop_scorecard as shop_scorecard_logic
from app.logic import names, price_tracker

router = APIRouter()


@router.get("/analytics/trends")
def analytics_trends(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return trends_payload(fetch_expenses_in_reporting_currency(db, user.id, scope, space_ids))


def trends_payload(expenses: list[dict]) -> dict:
    """Monthly totals, change and forecast for converted expenses (shared with /dashboard)."""
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


@router.get("/analytics/spending-mix")
def analytics_spending_mix(
    months: int = Query(default=spending_mix_logic.DEFAULT_MONTHS, ge=1, le=spending_mix_logic.MAX_MONTHS),
    top: int = Query(default=spending_mix_logic.MAX_ONE_OFFS, ge=1, le=50),
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Month by month: how much spending is committed, everyday, or a one-off.

    Committed means posted by a recurring template. A one-off is a purchase well above what is
    usual for its category (see app.logic.spending_mix). The three parts of each month add up
    to its total.
    """
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    result = spending_mix_logic.spending_mix(expenses, months=months, top=top)
    result["currency"] = get_reporting_currency(db, user.id)
    # Expenses left out because their currency has no exchange rate (same as the other totals).
    result["unconverted_count"] = unconverted
    return result


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


@router.get("/analytics/shops")
def analytics_shop_scorecard(
    months: int = Query(default=shop_scorecard_logic.DEFAULT_MONTHS, ge=0, le=60),
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Spend, visits and relative price level per shop over the last `months` months.

    `months=0` means all time. Shop and item names follow the user's saved merges, and
    names that differ only by case or spacing are one name.
    """
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    item_aliases, shop_aliases = load_alias_maps(db, user.id)
    # Bill totals name their shop in the description; make that the shop before the user's
    # shop merges are applied, so a merge covers them too.
    rows = names.canonicalise(shop_scorecard_logic.with_bill_shops(expenses), item_aliases, shop_aliases)
    result = shop_scorecard_logic.shop_scorecard(rows, months=months)
    result["currency"] = get_reporting_currency(db, user.id)
    result["unconverted_count"] = unconverted
    return result


def _price_rows(db: Session, user: models.User, item: str | None = None) -> tuple[list[dict], dict[str, str]]:
    """The user's expenses with their saved item/shop merges applied, plus the item
    aliases (so a request naming an old spelling still finds its merged item).

    With `item`, only that item's purchases are converted and returned (the detail views
    need one item, not every expense). Merged names are still decided from everything, so
    the result for that item is exactly what the full list would contain for it.
    """
    item_aliases, shop_aliases = load_alias_maps(db, user.id)
    rows, _ = convert_rows(
        db,
        user.id,
        # A bill recorded as a total is a shop trip, not an item's price: leave it out up front.
        [e for e in fetch_expenses(db, user.id) if not e["bill_total_only"]],
        select=lambda usable: names.canonicalise(usable, item_aliases, shop_aliases, only_item=item),
    )
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
    rows, item_aliases = _price_rows(db, user, item)
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
    rows, item_aliases = _price_rows(db, user, item)
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
    rows, item_aliases = _price_rows(db, user, item)
    return price_tracker.price_detail(rows, names.resolve_name(item, item_aliases), unit, category, brand, shop)
