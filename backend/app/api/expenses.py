import datetime
import io

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import ensure_options
from app.db.database import get_db
from app.db import models

router = APIRouter()

# Accepted header names (lowercased) for each field — supports the old
# dashboard's CSV/XLSX columns as well as the new ones.
_IMPORT_COLUMNS = {
    "date": ["date"],
    "category": ["category"],
    "subcategory": ["subcategory"],
    "description": ["item", "description"],
    "amount": ["pricepaid", "amount", "price"],
    "quantity": ["quantity", "qty"],
    "unit": ["quantityunit", "unit"],
    "shop": ["shop"],
    "brand": ["brand"],
    "currency": ["currency"],
}


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    category: str
    subcategory: str
    description: str
    amount: float
    quantity: float
    unit: str
    shop: str
    brand: str
    currency: str
    price_per_unit: float


class ExpenseCreate(BaseModel):
    date: datetime.date
    category: str = Field(min_length=1)
    subcategory: str = ""
    description: str = ""
    amount: float = Field(gt=0)
    quantity: float = Field(default=1.0, gt=0)
    unit: str = "Count"
    shop: str = ""
    brand: str = ""
    currency: str = "SEK"


class ExpenseUpdate(BaseModel):
    date: datetime.date | None = None
    category: str | None = Field(default=None, min_length=1)
    subcategory: str | None = None
    description: str | None = None
    amount: float | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    shop: str | None = None
    brand: str | None = None
    currency: str | None = None


def fetch_expenses(db: Session, user_id: int) -> list[dict]:
    """Shared accessor: a user's expenses as plain dicts for the logic modules."""
    rows = (
        db.query(models.Expense)
        .filter(models.Expense.user_id == user_id)
        .order_by(models.Expense.date)
        .all()
    )
    return [
        {
            "id": r.id,
            "date": r.date,
            "category": r.category,
            "subcategory": r.subcategory,
            "description": r.description,
            "amount": r.amount,
            "quantity": r.quantity,
            "unit": r.unit,
            "shop": r.shop,
            "brand": r.brand,
            "currency": r.currency,
            "price_per_unit": r.price_per_unit,
        }
        for r in rows
    ]


def _get_owned_or_404(db: Session, expense_id: int, user_id: int) -> models.Expense:
    expense = db.get(models.Expense, expense_id)
    if expense is None or expense.user_id != user_id:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Expense)
        .filter(models.Expense.user_id == user.id)
        .order_by(models.Expense.date)
        .all()
    )


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = models.Expense(user_id=user.id, **payload.model_dump())
    expense.price_per_unit = round(expense.amount / max(expense.quantity, 0.01), 2)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    # Auto-learn any new category/subcategory/unit/shop into the user's taxonomy.
    ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    return expense


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = _get_owned_or_404(db, expense_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)
    expense.price_per_unit = round(expense.amount / max(expense.quantity, 0.01), 2)
    db.commit()
    db.refresh(expense)
    ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    return expense


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = _get_owned_or_404(db, expense_id, user.id)
    db.delete(expense)
    db.commit()


@router.get("/expenses/summary")
def expenses_summary(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id)
    total = sum(e["amount"] for e in expenses)
    by_category: dict[str, float] = {}
    for e in expenses:
        by_category[e["category"]] = round(by_category.get(e["category"], 0.0) + e["amount"], 2)
    return {"total": round(total, 2), "count": len(expenses), "by_category": by_category}


def _cell(row, col):
    if col is None:
        return None
    value = row[col]
    return None if pd.isna(value) else value


@router.post("/expenses/import")
async def import_expenses(
    file: UploadFile = File(...),
    currency_override: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Import expenses from a CSV or Excel file (old-dashboard format supported).

    If currency_override is given, it is applied to every row (ignoring any
    Currency column in the file).
    """
    raw = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    header_lookup = {str(c).strip().lower(): c for c in df.columns}

    def col_for(field: str):
        for candidate in _IMPORT_COLUMNS[field]:
            if candidate in header_lookup:
                return header_lookup[candidate]
        return None

    date_c, cat_c, amt_c = col_for("date"), col_for("category"), col_for("amount")
    if not (date_c and cat_c and amt_c):
        raise HTTPException(
            status_code=400,
            detail="File must include at least Date, Category, and PricePaid/Amount columns.",
        )
    sub_c = col_for("subcategory")
    desc_c = col_for("description")
    qty_c = col_for("quantity")
    unit_c = col_for("unit")
    shop_c = col_for("shop")
    brand_c = col_for("brand")
    cur_c = col_for("currency")

    # Dedup against existing expenses (date, category, description, amount).
    existing = {
        (str(e["date"]), (e["category"] or "").strip().lower(), (e["description"] or "").strip().lower(), round(float(e["amount"]), 2))
        for e in fetch_expenses(db, user.id)
    }

    added = skipped = 0
    errors: list[str] = []
    learned: set[tuple] = set()

    for idx, row in df.iterrows():
        try:
            parsed = pd.to_datetime(_cell(row, date_c), errors="coerce")
            category = _cell(row, cat_c)
            amount_raw = _cell(row, amt_c)
            if pd.isna(parsed) or category is None or amount_raw is None:
                skipped += 1
                continue
            when = parsed.date()
            category = str(category).strip()
            amount = float(amount_raw)
            if not category or amount <= 0:
                skipped += 1
                continue

            description = str(_cell(row, desc_c) or "").strip()
            subcategory = str(_cell(row, sub_c) or "").strip()
            qty_val = _cell(row, qty_c)
            quantity = float(qty_val) if qty_val is not None else 1.0
            if quantity <= 0:
                quantity = 1.0
            unit = str(_cell(row, unit_c) or "Count").strip() or "Count"
            shop = str(_cell(row, shop_c) or "").strip()
            brand = str(_cell(row, brand_c) or "").strip()
            currency = str(_cell(row, cur_c) or "SEK").strip() or "SEK"
            if currency_override.strip():
                currency = currency_override.strip().upper()

            key = (str(when), category.lower(), description.lower(), round(amount, 2))
            if key in existing:
                skipped += 1
                continue
            existing.add(key)

            expense = models.Expense(
                user_id=user.id,
                date=when,
                category=category,
                subcategory=subcategory,
                description=description,
                amount=amount,
                quantity=quantity,
                unit=unit,
                shop=shop,
                brand=brand,
                currency=currency,
            )
            expense.price_per_unit = round(amount / max(quantity, 0.01), 2)
            db.add(expense)
            learned.add((category, subcategory, unit, shop))
            added += 1
        except Exception as exc:  # noqa: BLE001 — report row-level issues, keep going
            if len(errors) < 20:
                errors.append(f"Row {int(idx) + 2}: {exc}")

    db.commit()
    for category, subcategory, unit, shop in learned:
        ensure_options(db, user.id, category, subcategory, unit, shop)

    return {"added": added, "skipped": skipped, "errors": errors}


@router.get("/expenses/export")
def export_expenses(
    format: str = "csv",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows = fetch_expenses(db, user.id)
    df = pd.DataFrame(
        [
            {
                "Date": r["date"],
                "Category": r["category"],
                "Subcategory": r["subcategory"],
                "Item": r["description"],
                "Shop": r["shop"],
                "Brand": r["brand"],
                "PricePaid": r["amount"],
                "Quantity": r["quantity"],
                "QuantityUnit": r["unit"],
                "PricePerUnit": r["price_per_unit"],
                "Currency": r["currency"],
            }
            for r in rows
        ]
    )

    if format == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Expenses")
        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=expenses.xlsx"},
        )

    return Response(
        content=df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )
