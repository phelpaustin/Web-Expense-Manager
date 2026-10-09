import datetime
import io
from decimal import Decimal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_group_ids, is_group_member, require_role_at_least
from app.api.options import (
    convert_rows,
    default_currency_for,
    ensure_options,
    get_or_create_options,
    get_reporting_currency,
)
from app.core import fx
from app.core.currency import normalize_currency
from app.core.fx import normalize_convertible_currency
from app.core.file_upload import read_upload_limited
from app.core.import_limits import MAX_IMPORT_FILE_BYTES, MAX_IMPORT_ROWS
from app.core.parsing import parse_amount, read_csv_bytes
from app.core.validation import PartialUpdate
from app.core.money import as_decimal, quantize_money, MAX_MONEY
from app.db.database import get_db
from app.db import models
from app.logic import categorizer
from app.logic import currency as currency_logic

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
    amount: Decimal
    quantity: float
    unit: str
    shop: str
    brand: str
    currency: str
    price_per_unit: Decimal
    group_id: int | None = None


class ExpenseCreate(BaseModel):
    date: datetime.date
    category: str = Field(min_length=1)
    subcategory: str = ""
    description: str = ""
    amount: Decimal = Field(gt=0, le=MAX_MONEY)
    quantity: float = Field(default=1.0, gt=0)
    unit: str = "Count"
    shop: str = ""
    brand: str = ""
    # None = use the default: the space's currency, else the user's base currency.
    currency: str | None = None
    group_id: int | None = None

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None


class ExpenseUpdate(PartialUpdate):
    # group_id may be null (move the expense back to personal); everything else is NOT NULL.
    not_nullable = frozenset(
        {"date", "category", "subcategory", "description", "amount", "quantity", "unit", "shop", "brand", "currency"}
    )
    date: datetime.date | None = None
    category: str | None = Field(default=None, min_length=1)
    subcategory: str | None = None
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    shop: str | None = None
    brand: str | None = None
    currency: str | None = None
    group_id: int | None = None

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None


class ExpenseBulkCreate(BaseModel):
    items: list[ExpenseCreate] = Field(min_length=1)


def _price_per_unit(amount: Decimal, quantity: float) -> Decimal:
    divisor = max(as_decimal(quantity), Decimal("0.01"))
    return (amount / divisor).quantize(Decimal("0.0001"))


def _visible_expenses_query(db: Session, user_id: int, scope: str | None = None, space_ids: str | None = None):
    """Query of Expense rows this user can see, before any extra filtering/pagination.

    space_ids (comma-separated: "personal", group ids, or both) selects a combined
    view across several Expense Spaces and takes priority over scope when given.
    Otherwise scope controls which expenses are included:
      - None / "all" (default): the user's own expenses + every space they belong to.
      - "personal": only the user's own, unassigned-to-a-space expenses.
      - "<space id>": only that one Expense Space's expenses (caller must have
        already verified the user is a member — non-members get an empty list).

    Returns None when the requested scope resolves to no visible expenses at all.
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
            return None
        return db.query(models.Expense).filter(or_(*conditions))
    elif scope == "personal":
        return db.query(models.Expense).filter(
            models.Expense.user_id == user_id, models.Expense.group_id.is_(None)
        )
    elif scope and scope != "all":
        try:
            requested_group_id = int(scope)
        except ValueError:
            requested_group_id = None
        if requested_group_id is None or requested_group_id not in group_ids:
            return None
        return db.query(models.Expense).filter(models.Expense.group_id == requested_group_id)
    else:
        visibility = models.Expense.user_id == user_id
        if group_ids:
            visibility = or_(visibility, models.Expense.group_id.in_(group_ids))
        return db.query(models.Expense).filter(visibility)


def fetch_expenses(
    db: Session, user_id: int, scope: str | None = None, space_ids: str | None = None
) -> list[dict]:
    """Shared accessor: every expense this user can see, as plain dicts for the logic
    modules (analytics/budgets/alerts/metrics all need the full set to aggregate
    correctly, so this is intentionally unpaginated — see list_expenses for the
    paginated version used by the expenses list page).
    """
    q = _visible_expenses_query(db, user_id, scope, space_ids)
    if q is None:
        return []
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


def fetch_expenses_in_reporting_currency_ex(
    db: Session, user_id: int, scope: str | None = None, space_ids: str | None = None
) -> tuple[list[dict], int]:
    """Rows converted into the user's reporting (display) currency, plus how many were skipped.

    Expenses whose currency has no exchange rate are left out of the aggregate
    (and counted) rather than failing the whole request, so one bad row can't
    take every dashboard endpoint down for the user or a shared space.
    """
    return convert_rows(db, user_id, fetch_expenses(db, user_id, scope, space_ids))


def fetch_expenses_in_reporting_currency(
    db: Session, user_id: int, scope: str | None = None, space_ids: str | None = None
) -> list[dict]:
    """Same rows as fetch_expenses, but every amount converted into the user's
    reporting currency — analytics/budgets/metrics/alerts need one common unit to
    aggregate across currencies (see app/logic/currency.py + app/core/fx.py).
    Unconvertible rows are skipped; use fetch_expenses_in_reporting_currency_ex to
    also learn how many.
    """
    return fetch_expenses_in_reporting_currency_ex(db, user_id, scope, space_ids)[0]


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


def _require_group_write_access(
    db: Session, group_id: int | None, user_id: int, expense_owner_id: int | None = None
) -> None:
    """Owners/admins may write any expense in the space; editors only their own; viewers none."""
    if group_id is None:
        return
    member = require_role_at_least(db, group_id, user_id, "editor", "Viewers can't add or edit expenses in this space")
    if member.role == "editor" and expense_owner_id is not None and expense_owner_id != user_id:
        raise HTTPException(status_code=403, detail="Editors can only edit or delete their own expenses in this space")


@router.get("/expenses")
def list_expenses(
    scope: str | None = None,
    space_ids: str | None = None,
    search: str | None = None,
    category: str | None = None,
    shop: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Paginated + filtered expense list for the expenses page. Analytics/budgets/
    alerts/metrics use fetch_expenses() instead — they need the full, unpaginated set.
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)

    q = _visible_expenses_query(db, user.id, scope, space_ids)
    if q is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    if category:
        q = q.filter(models.Expense.category == category)
    if shop:
        q = q.filter(models.Expense.shop == shop)
    if date_from:
        q = q.filter(models.Expense.date >= date_from)
    if date_to:
        q = q.filter(models.Expense.date <= date_to)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.Expense.description.ilike(like),
                models.Expense.shop.ilike(like),
                models.Expense.brand.ilike(like),
                models.Expense.category.ilike(like),
                models.Expense.subcategory.ilike(like),
            )
        )

    total = q.count()
    rows = (
        q.order_by(models.Expense.date.desc(), models.Expense.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    creator_ids = {r.user_id for r in rows if r.group_id is not None and r.user_id is not None}
    creators = {}
    if creator_ids:
        for u in db.query(models.User).filter(models.User.id.in_(creator_ids)).all():
            creators[u.id] = u.name or u.email

    items = [
        {
            "id": r.id,
            "date": r.date.isoformat(),
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
            "created_by": (
                (creators.get(r.user_id) or "Deleted user") if r.user_id is not None else "Deleted user"
            ) if r.group_id is not None else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_group_write_access(db, payload.group_id, user.id)
    data = payload.model_dump()
    data["currency"] = data["currency"] or default_currency_for(db, user.id, payload.group_id)
    expense = models.Expense(user_id=user.id, **data)
    expense.price_per_unit = _price_per_unit(expense.amount, expense.quantity)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    # Auto-learn any new category/subcategory/unit/shop into the user's taxonomy.
    ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    return expense


@router.post("/expenses/bulk", response_model=list[ExpenseOut], status_code=201)
def create_expenses_bulk(
    payload: ExpenseBulkCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Add several line items from a single bill/receipt in one request."""
    for item in payload.items:
        _require_group_write_access(db, item.group_id, user.id)

    created: list[models.Expense] = []
    for item in payload.items:
        data = item.model_dump()
        data["currency"] = data["currency"] or default_currency_for(db, user.id, item.group_id)
        expense = models.Expense(user_id=user.id, **data)
        expense.price_per_unit = _price_per_unit(expense.amount, expense.quantity)
        db.add(expense)
        created.append(expense)
    db.commit()
    for expense in created:
        db.refresh(expense)
        ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    return created


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = _get_visible_or_404(db, expense_id, user.id)
    _require_group_write_access(db, expense.group_id, user.id, expense.user_id)
    data = payload.model_dump(exclude_unset=True)
    if "group_id" in data:
        _require_group_write_access(db, data["group_id"], user.id, expense.user_id)
    for field, value in data.items():
        setattr(expense, field, value)
    expense.price_per_unit = _price_per_unit(expense.amount, expense.quantity)
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
    _require_group_write_access(db, expense.group_id, user.id, expense.user_id)
    db.delete(expense)
    db.commit()


@router.get("/expenses/summary")
def expenses_summary(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    reporting = get_reporting_currency(db, user.id)
    total = sum(e["amount"] for e in expenses)
    by_category: dict[str, Decimal] = {}
    for e in expenses:
        by_category[e["category"]] = round(by_category.get(e["category"], Decimal("0")) + e["amount"], 2)
    return {
        "total": round(total, 2),
        "count": len(expenses),
        "by_category": by_category,
        "currency": reporting,
        # Expenses left out of the totals because their currency can't be converted.
        "unconverted_count": unconverted,
    }


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
    default_currency = get_or_create_options(db, user.id).base_currency or "SEK"
    override = currency_override.strip()
    if override:
        try:
            override = normalize_convertible_currency(override)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are allowed")
    raw = await read_upload_limited(file, MAX_IMPORT_FILE_BYTES)
    try:
        if name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(raw), nrows=MAX_IMPORT_ROWS + 1)
        else:
            df = read_csv_bytes(raw, nrows=MAX_IMPORT_ROWS + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")
    if len(df.index) > MAX_IMPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"File has more than {MAX_IMPORT_ROWS:,} data rows")

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

    # Currency is part of expense identity: equal numeric amounts in distinct
    # currencies are not duplicates.
    existing = {
        (
            str(e["date"]),
            (e["category"] or "").strip().lower(),
            (e["description"] or "").strip().lower(),
            quantize_money(e["amount"]),
            normalize_currency(e.get("currency") or "SEK"),
        )
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
                amount = quantize_money(parse_amount(amount_raw))
            except (TypeError, ValueError, ArithmeticError):
                record_skip(row, "Amount is not a number", line)
                continue
            if amount <= 0:
                record_skip(row, "Amount must be greater than 0", line)
                continue

            description = str(_cell(row, desc_c) or "").strip()
            subcategory = str(_cell(row, sub_c) or "").strip()
            qty_val = _cell(row, qty_c)
            try:
                quantity = float(parse_amount(qty_val)) if qty_val is not None else 1.0
            except (TypeError, ValueError, ArithmeticError):
                quantity = 1.0
            if quantity <= 0:
                quantity = 1.0
            unit = str(_cell(row, unit_c) or "Count").strip() or "Count"
            shop = str(_cell(row, shop_c) or "").strip()
            brand = str(_cell(row, brand_c) or "").strip()
            currency = str(_cell(row, cur_c) or default_currency).strip() or default_currency
            if override:
                currency = override
            try:
                currency = normalize_convertible_currency(currency)
            except ValueError:
                record_skip(row, f"Unsupported currency code: {currency}", line)
                continue

            key = (str(when), category.lower(), description.lower(), amount, currency)
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
            expense.price_per_unit = _price_per_unit(amount, quantity)
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
