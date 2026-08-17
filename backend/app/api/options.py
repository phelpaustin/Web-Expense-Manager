"""Per-user dropdown options (categories, subcategories, units) with add-new.

Ported from the old dropdown_options.json + ui_components.py behavior. Each
user gets their own editable taxonomy, seeded with sensible defaults.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models

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


def get_or_create_options(db: Session, user_id: int) -> models.UserOptions:
    opts = (
        db.query(models.UserOptions)
        .filter(models.UserOptions.user_id == user_id)
        .first()
    )
    if opts is None:
        opts = models.UserOptions(
            user_id=user_id,
            categories=list(DEFAULT_CATEGORIES),
            subcategories={k: list(v) for k, v in DEFAULT_SUBCATEGORIES.items()},
            units=list(DEFAULT_UNITS),
            shops=list(DEFAULT_SHOPS),
        )
        db.add(opts)
        db.commit()
        db.refresh(opts)
    return opts


def _serialize(opts: models.UserOptions) -> dict:
    return {
        "categories": opts.categories or [],
        "subcategories": opts.subcategories or {},
        "units": opts.units or [],
        "shops": opts.shops or [],
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

    if category and category not in categories:
        categories.append(category)
        changed = True
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
    if payload.name not in cats:
        cats.append(payload.name)
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
    if payload.category not in cats:
        cats.append(payload.category)
        opts.categories = sorted(cats)
    entries = list(subs.get(payload.category, []))
    if payload.name not in entries:
        entries.append(payload.name)
        subs[payload.category] = sorted(entries)
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
