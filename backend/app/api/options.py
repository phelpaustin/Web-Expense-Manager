"""Per-user dropdown options (categories, subcategories, units) with add-new.

Ported from the old dropdown_options.json + ui_components.py behavior. Each
user gets their own editable taxonomy, seeded with sensible defaults.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import fx
from app.core.fx import normalize_convertible_currency
from app.db.database import get_db
from app.db import models
from app.logic import currency as currency_logic
from app.logic.taxonomy import clean_category, find_existing

router = APIRouter()

DEFAULT_CATEGORIES = [
    "Alcohol", "Baby Shopping", "Bags", "Bakery", "Baking", "Cutlery", "Dairy",
    "Dine-Out", "Fruits", "Furnishing & Decor", "Gardening", "Groceries",
    "Household", "Ice Cream", "Juices", "Kitchen Accessories", "Masala", "Meat",
    "Oil", "Personal Care and Hygiene", "Photos", "Picnic Things", "Salads",
    "Seafood", "Snacks", "Spices", "Spreads", "Stationary", "Toiletries", "Vegetable",
]

DEFAULT_SUBCATEGORIES = {
    "Bakery": ["Bread", "Cake"],
    "Dairy": ["Cheese", "Milk", "Cream"],
    "Dine-Out": ["Dinner", "Lunch"],
    "Groceries": ["Dry Fruits", "Noodles", "Rice"],
    "Meat": ["Chicken", "Egg", "Frozen", "Mutton", "Pork"],
    "Picnic Things": ["Grilling Accessories"],
    "Seafood": ["Prawns"],
    "Toiletries": ["Cleaning", "Washing"],
    "Vegetable": ["Frozen", "Indian Vegetables", "Salad"],
    "Personal Care and Hygiene": [
        "Fragrances", "Grooming", "Hair Care", "Laundry", "Oral Hygiene",
        "Sanitary Pads", "Skin Care", "Soaps & Shampoos",
    ],
    "Baby Shopping": ["Baby Gear", "Clothes", "Creams", "Diapers", "Food", "Soaps & Shampoo"],
    "Baking": ["Cutlery"],
}

DEFAULT_UNITS = ["Count", "Kg", "Litre", "Meter"]

DEFAULT_SHOPS = [
    "Coop", "Costco", "ICA", "IKEA", "Lidl", "Systembolaget", "Willys",
]


def _find_options(db: Session, user_id: int) -> models.UserOptions | None:
    return db.query(models.UserOptions).filter(models.UserOptions.user_id == user_id).first()


def get_or_create_options(db: Session, user_id: int) -> models.UserOptions:
    """The user's options row, created with defaults on first use.

    The dashboard fires many requests in parallel on a new user's first load, and
    each one calls this. A plain select-then-insert lets several of them insert the
    same row and all but one fail on the unique user_id constraint (a 500). The
    insert is therefore ``ON CONFLICT DO NOTHING``, after which every caller simply
    reads the one row that exists. It needs no rollback, so it cannot discard
    anything else the caller has pending in the session.
    """
    opts = _find_options(db, user_id)
    if opts is not None:
        return opts

    values = {
        "user_id": user_id,
        "categories": list(DEFAULT_CATEGORIES),
        "subcategories": {k: list(v) for k, v in DEFAULT_SUBCATEGORIES.items()},
        "units": list(DEFAULT_UNITS),
        "shops": list(DEFAULT_SHOPS),
        "base_currency": "SEK",
    }
    dialect = db.get_bind().dialect.name
    if dialect in ("postgresql", "sqlite"):
        insert = postgresql_insert if dialect == "postgresql" else sqlite_insert
        db.execute(insert(models.UserOptions.__table__).values(**values).on_conflict_do_nothing(index_elements=["user_id"]))
        db.commit()
    else:
        # Other databases: fall back to insert-and-recover.
        try:
            db.add(models.UserOptions(**values))
            db.commit()
        except IntegrityError:
            db.rollback()

    opts = _find_options(db, user_id)
    if opts is None:  # the row is gone again (e.g. account deleted meanwhile)
        raise HTTPException(status_code=404, detail="User not found")
    return opts


def default_currency_for(db: Session, user_id: int, group_id: int | None = None) -> str:
    """Currency a new record should default to: the space's currency when it is
    filed under one, otherwise the user's personal (base) currency."""
    if group_id is not None:
        group = db.get(models.Group, group_id)
        if group is not None and group.currency:
            return group.currency
    return get_or_create_options(db, user_id).base_currency or "SEK"


def reporting_currency(opts: models.UserOptions) -> str:
    """Currency totals, budgets and alerts are shown in.

    The user's display currency when they set one, otherwise their base currency.
    (The base currency is separate: it is only the default for *new* records.)
    """
    return opts.display_currency or opts.base_currency or "SEK"


def get_reporting_currency(db: Session, user_id: int) -> str:
    return reporting_currency(get_or_create_options(db, user_id))


def convert_rows(
    db: Session, user_id: int, rows: list[dict], target: str | None = None
) -> tuple[list[dict], int]:
    """Convert dict rows (date/amount/currency) into ``target`` (default: the
    user's reporting currency).

    Uses each row's own date for the exchange rate. Rows whose currency can't be
    converted are left out and counted instead of failing the whole request.
    """
    target = target or get_reporting_currency(db, user_id)
    fx.ensure_rates_for(rows, target)
    try:
        return currency_logic.convert_expenses_partial(rows, target, fx.get_rate)
    except currency_logic.CurrencyConversionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _serialize(opts: models.UserOptions) -> dict:
    return {
        "categories": opts.categories or [],
        "subcategories": opts.subcategories or {},
        "units": opts.units or [],
        "shops": opts.shops or [],
        # Default currency for NEW records (expenses, income, bills, ...).
        "base_currency": opts.base_currency or "SEK",
        # Currency every total/budget/alert is shown in; follows base unless the user chose one.
        "display_currency": reporting_currency(opts),
        "display_currency_is_custom": opts.display_currency is not None,
        # New bills are recorded as total-only expenses straight away (so budgets include them).
        "count_bills_as_spending": bool(opts.count_bills_as_spending),
        # Daily budget-alert digest email (off after unsubscribing).
        "alert_digest_enabled": bool(opts.alert_digest_enabled),
        # Currencies a record can be entered in (those with an exchange rate).
        "currencies": sorted(fx.supported_currencies()),
    }


def ensure_options(
    db: Session,
    user_id: int,
    category: str,
    subcategory: str,
    unit: str,
    shop: str = "",
) -> None:
    """Auto-learn: add any unseen category/subcategory/unit/shop to the taxonomy."""
    opts = get_or_create_options(db, user_id)
    categories = list(opts.categories or [])
    subcats = dict(opts.subcategories or {})
    units = list(opts.units or [])
    shops = list(opts.shops or [])
    changed = False

    if category:
        listed = find_existing(categories, category)
        if listed is None:
            categories.append(clean_category(category))
            changed = True
        else:
            category = listed  # a case variant of a listed category: file under the listed spelling
    if category and subcategory:
        subs = list(subcats.get(category, []))
        if subcategory not in subs:
            subs.append(subcategory)
            subcats[category] = subs
            changed = True
    if unit and unit not in units:
        units.append(unit)
        changed = True
    if shop and shop not in shops:
        shops.append(shop)
        changed = True

    if changed:
        # Reassign so SQLAlchemy detects the JSON change.
        opts.categories = sorted(categories)
        opts.subcategories = subcats
        opts.units = units
        opts.shops = sorted(shops)
        db.commit()


class CategoryIn(BaseModel):
    name: str = Field(min_length=1)


class SubcategoryIn(BaseModel):
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)


class UnitIn(BaseModel):
    name: str = Field(min_length=1)


class ShopIn(BaseModel):
    name: str = Field(min_length=1)


class CurrencyIn(BaseModel):
    currency: str = Field(min_length=1, max_length=8)

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str) -> str:
        return normalize_convertible_currency(value)


class DisplayCurrencyIn(BaseModel):
    # None resets to "follow the base currency".
    currency: str | None = Field(default=None, max_length=8)

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None


def canonical_category(db: Session, user_id: int, name: str) -> str:
    """`name` spelled the way the user's category list spells it (or just tidied, if new)."""
    opts = get_or_create_options(db, user_id)
    return find_existing(list(opts.categories or []), name) or clean_category(name)


@router.get("/options")
def get_options(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _serialize(get_or_create_options(db, user.id))


@router.post("/options/category")
def add_category(
    payload: CategoryIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    cats = list(opts.categories or [])
    name = clean_category(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Category name can't be blank.")
    existing = find_existing(cats, name)
    if existing is not None:
        # "milk" or "MILK" when "Milk" exists: say so rather than make a near-duplicate.
        raise HTTPException(status_code=409, detail=f"“{existing}” is already present.")
    cats.append(name)
    opts.categories = sorted(cats)
    db.commit()
    return _serialize(opts)


@router.post("/options/subcategory")
def add_subcategory(
    payload: SubcategoryIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    cats = list(opts.categories or [])
    subs = dict(opts.subcategories or {})
    category = find_existing(cats, payload.category)  # a case variant files under the listed one
    if category is None:
        category = clean_category(payload.category)
        cats.append(category)
        opts.categories = sorted(cats)
    entries = list(subs.get(category, []))
    if payload.name not in entries:
        entries.append(payload.name)
        subs[category] = sorted(entries)
        opts.subcategories = subs
    db.commit()
    return _serialize(opts)


@router.post("/options/unit")
def add_unit(
    payload: UnitIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    units = list(opts.units or [])
    if payload.name not in units:
        units.append(payload.name)
        opts.units = units
        db.commit()
    return _serialize(opts)


@router.post("/options/shop")
def add_shop(
    payload: ShopIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    shops = list(opts.shops or [])
    if payload.name not in shops:
        shops.append(payload.name)
        opts.shops = sorted(shops)
        db.commit()
    return _serialize(opts)


@router.delete("/options/category/{name}")
def delete_category(
    name: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    opts.categories = [c for c in (opts.categories or []) if c != name]
    subs = dict(opts.subcategories or {})
    subs.pop(name, None)
    opts.subcategories = subs
    db.commit()
    return _serialize(opts)


@router.delete("/options/subcategory/{category}/{name}")
def delete_subcategory(
    category: str,
    name: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    subs = dict(opts.subcategories or {})
    if category in subs:
        subs[category] = [s for s in subs[category] if s != name]
        opts.subcategories = subs
        db.commit()
    return _serialize(opts)


@router.delete("/options/unit/{name}")
def delete_unit(
    name: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    opts.units = [u for u in (opts.units or []) if u != name]
    db.commit()
    return _serialize(opts)


@router.delete("/options/shop/{name}")
def delete_shop(
    name: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    opts.shops = [s for s in (opts.shops or []) if s != name]
    db.commit()
    return _serialize(opts)


@router.post("/options/base-currency")
def set_base_currency(
    payload: CurrencyIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    opts = get_or_create_options(db, user.id)
    opts.base_currency = payload.currency.strip().upper()
    db.commit()
    return _serialize(opts)


class BillsSettingIn(BaseModel):
    enabled: bool


@router.post("/options/count-bills-as-spending")
def set_count_bills_as_spending(
    payload: BillsSettingIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Turn "count new bills as spending straight away" on or off."""
    opts = get_or_create_options(db, user.id)
    opts.count_bills_as_spending = payload.enabled
    db.commit()
    return _serialize(opts)


@router.post("/options/alert-digest")
def set_alert_digest(
    payload: BillsSettingIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Turn the budget-alert digest email on or off."""
    opts = get_or_create_options(db, user.id)
    opts.alert_digest_enabled = payload.enabled
    db.commit()
    return _serialize(opts)


@router.post("/options/display-currency")
def set_display_currency(
    payload: DisplayCurrencyIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Choose the currency totals are shown in. Changes no stored data; send
    ``{"currency": null}`` to follow the base currency again."""
    opts = get_or_create_options(db, user.id)
    opts.display_currency = payload.currency
    db.commit()
    return _serialize(opts)
