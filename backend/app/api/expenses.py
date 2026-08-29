import datetime
import io

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_group_ids, is_group_member, require_role_at_least
from app.api.options import ensure_options
from app.db.database import get_db
from app.db import models
from app.logic import categorizer

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
    group_id: int | None = None


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
    group_id: int | None = None


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
    group_id: int | None = None


def fetch_expenses(
    db: Session, user_id: int, scope: str | None = None, space_ids: str | None = None
) -> list[dict]:
    """Shared accessor: expenses this user can see, as plain dicts for the logic modules.

    space_ids (comma-separated: "personal", group ids, or both) selects a combined
    view across several Expense Spaces and takes priority over scope when given.
    Otherwise scope controls which expenses are included:
      - None / "all" (default): the user's own expenses + every space they belong to.
      - "personal": only the user's own, unassigned-to-a-space expenses.
      - "<space id>": only that one Expense Space's expenses (caller must have
        already verified the user is a member — non-members get an empty list).
    """
    group_ids = get_user_group_ids(db, user_id)

    if space_ids:
        requested = [s.strip() for s in space_ids.split(",") if s.strip()]
        include_personal = "personal" in requested
        requested_group_ids = []
        for s in requested:
            if s == "personal":
                continue
            try:
                gid = int(s)
            except ValueError:
                continue
            if gid in group_ids:
                requested_group_ids.append(gid)

        conditions = []
        if include_personal:
            conditions.append(and_(models.Expense.user_id == user_id, models.Expense.group_id.is_(None)))
        if requested_group_ids:
            conditions.append(models.Expense.group_id.in_(requested_group_ids))
        if not conditions:
            return []
        q = db.query(models.Expense).filter(or_(*conditions))
    elif scope == "personal":
        q = db.query(models.Expense).filter(
            models.Expense.user_id == user_id, models.Expense.group_id.is_(None)
        )
    elif scope and scope != "all":
        try:
            requested_group_id = int(scope)
        except ValueError:
            requested_group_id = None
        if requested_group_id is None or requested_group_id not in group_ids:
            return []
        q = db.query(models.Expense).filter(models.Expense.group_id == requested_group_id)
    else:
        visibility = models.Expense.user_id == user_id
        if group_ids:
            visibility = or_(visibility, models.Expense.group_id.in_(group_ids))
        q = db.query(models.Expense).filter(visibility)

    rows = q.order_by(models.Expense.date).all()
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
            "group_id": r.group_id,
            "user_id": r.user_id,
        }
        for r in rows
    ]


def _get_visible_or_404(db: Session, expense_id: int, user_id: int) -> models.Expense:
    """An expense the user owns, or that belongs to a group they're a member of."""
    expense = db.get(models.Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    owns_it = expense.user_id == user_id
    in_shared_group = expense.group_id is not None and is_group_member(db, expense.group_id, user_id)
    if not (owns_it or in_shared_group):
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


def _require_group_write_access(db: Session, group_id: int | None, user_id: int) -> None:
    if group_id is not None:
        require_role_at_least(db, group_id, user_id, "editor", "Viewers can't add or edit expenses in this space")


@router.get("/expenses")
def list_expenses(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id)
    creator_ids = {e["user_id"] for e in expenses if e["group_id"] is not None}
    creators = {}
    if creator_ids:
        for u in db.query(models.User).filter(models.User.id.in_(creator_ids)).all():
            creators[u.id] = u.name or u.email
    for e in expenses:
        e["created_by"] = creators.get(e["user_id"]) if e["group_id"] is not None else None
        e["date"] = e["date"].isoformat()
        del e["user_id"]
    return expenses


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_group_write_access(db, payload.group_id, user.id)
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
    expense = _get_visible_or_404(db, expense_id, user.id)
    _require_group_write_access(db, expense.group_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "group_id" in data:
        _require_group_write_access(db, data["group_id"], user.id)
    for field, value in data.items():
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
    expense = _get_visible_or_404(db, expense_id, user.id)
    _require_group_write_access(db, expense.group_id, user.id)
    db.delete(expense)
    db.commit()


@router.get("/expenses/summary")
def expenses_summary(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses = fetch_expenses(db, user.id, scope, space_ids)
    total = sum(e["amount"] for e in expenses)
    by_category: dict[str, float] = {}
    for e in expenses:
        by_category[e["category"]] = round(by_category.get(e["category"], 0.0) + e["amount"], 2)
    return {"total": round(total, 2), "count": len(expenses), "by_category": by_category}


@router.get("/expenses/categorize/suggest")
def suggest_category(
    description: str = "",
    shop: str = "",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return categorizer.suggest_category(fetch_expenses(db, user.id), description, shop)


@router.post("/expenses/categorize/auto")
def auto_categorize(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Fill in category (+ subcategory) for expenses currently missing one."""
    expenses = fetch_expenses(db, user.id)
    suggestions = categorizer.auto_categorize_missing(expenses)
    for expense_id, category, subcategory in suggestions:
        expense = db.get(models.Expense, expense_id)
        if expense and expense.user_id == user.id:
            expense.category = category
            if subcategory and not expense.subcategory:
                expense.subcategory = subcategory
            ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    db.commit()
    return {"updated": len(suggestions)}



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
    skipped_rows: list[dict] = []
    learned: set[tuple] = set()

    def raw_row(row, reason: str, line: int) -> dict:
        def s(col):
            v = _cell(row, col)
            return "" if v is None else str(v)

        return {
            "line": line,
            "reason": reason,
            "date": s(date_c),
            "category": s(cat_c),
            "subcategory": s(sub_c),
            "description": s(desc_c),
            "amount": s(amt_c),
            "quantity": s(qty_c),
            "unit": s(unit_c),
            "shop": s(shop_c),
            "brand": s(brand_c),
            "currency": s(cur_c),
        }

    def record_skip(row, reason: str, line: int):
        nonlocal skipped
        skipped += 1
        if len(skipped_rows) < 200:
            skipped_rows.append(raw_row(row, reason, line))

    for idx, row in df.iterrows():
        line = int(idx) + 2
        try:
            parsed = pd.to_datetime(_cell(row, date_c), errors="coerce")
            category = _cell(row, cat_c)
            amount_raw = _cell(row, amt_c)
            if pd.isna(parsed):
                record_skip(row, "Invalid or missing date", line)
                continue
            if category is None or not str(category).strip():
                record_skip(row, "Missing category", line)
                continue
            when = parsed.date()
            category = str(category).strip()
            try:
                amount = float(amount_raw)
            except (TypeError, ValueError):
                record_skip(row, "Amount is not a number", line)
                continue
            if amount <= 0:
                record_skip(row, "Amount must be greater than 0", line)
                continue

            description = str(_cell(row, desc_c) or "").strip()
            subcategory = str(_cell(row, sub_c) or "").strip()
            qty_val = _cell(row, qty_c)
            try:
                quantity = float(qty_val) if qty_val is not None else 1.0
            except (TypeError, ValueError):
                quantity = 1.0
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
                record_skip(row, "Duplicate of an existing expense", line)
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
            record_skip(row, str(exc), line)
            if len(errors) < 20:
                errors.append(f"Row {line}: {exc}")

    db.commit()
    for category, subcategory, unit, shop in learned:
        ensure_options(db, user.id, category, subcategory, unit, shop)

    return {"added": added, "skipped": skipped, "errors": errors, "skipped_rows": skipped_rows}


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
