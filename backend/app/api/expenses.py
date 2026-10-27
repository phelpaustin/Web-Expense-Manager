import datetime
import io
from decimal import Decimal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import and_, func, or_
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
from app.core.file_upload import ensure_xlsx_within_limits, read_upload_limited_sync
from app.core.import_limits import MAX_IMPORT_FILE_BYTES, MAX_IMPORT_ROWS
from app.api import bill_sync
from app.core.parsing import escape_formula, parse_amount, read_csv_bytes, unescape_formula
from app.core.validation import Name, OptionalName, PartialUpdate, Text
from app.core.money import as_decimal, quantize_money, MAX_MONEY, JsonDecimal
from app.db.database import get_db
from app.db import models
from app.logic import categorizer
from app.logic.search import LIKE_ESCAPE, like_pattern
from app.logic.taxonomy import CategoryResolver
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


MAX_COVER_DAYS = 366


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    category: str
    subcategory: str
    description: str
    amount: JsonDecimal
    quantity: float
    unit: str
    shop: str
    brand: str
    currency: str
    price_per_unit: JsonDecimal
    group_id: int | None = None
    # Set when the expense came from a bill; bill_total_only marks the one-line "Record total".
    source_bill_id: int | None = None
    bill_total_only: bool = False
    # Set when a recurring template posted it (a committed payment, not an everyday purchase).
    recurring_template_id: int | None = None
    # Trip expenses: the first and last trip day this expense covers (null = the day it was paid).
    covers_from: datetime.date | None = None
    covers_to: datetime.date | None = None


class ExpenseCreate(BaseModel):
    date: datetime.date
    category: Name
    subcategory: OptionalName = ""
    description: Text = ""
    amount: Decimal = Field(gt=0, le=MAX_MONEY)
    quantity: float = Field(default=1.0, gt=0)
    unit: OptionalName = "Count"
    shop: OptionalName = ""
    brand: OptionalName = ""
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
    category: Name | None = None
    subcategory: OptionalName | None = None
    description: Text | None = None
    amount: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)
    quantity: float | None = Field(default=None, gt=0)
    unit: OptionalName | None = None
    shop: OptionalName | None = None
    brand: OptionalName | None = None
    currency: str | None = None
    group_id: int | None = None
    # Both together: the stretch of the trip this expense covers, or both null to clear it.
    covers_from: datetime.date | None = None
    covers_to: datetime.date | None = None

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        return normalize_convertible_currency(value) if value is not None else None

    @model_validator(mode="after")
    def _covers_together(self):
        given = {"covers_from", "covers_to"} & self.model_fields_set
        if not given:
            return self
        if given != {"covers_from", "covers_to"}:
            raise ValueError("send covers_from and covers_to together")
        if (self.covers_from is None) != (self.covers_to is None):
            raise ValueError("covers_from and covers_to must both be dates, or both null")
        if self.covers_from is not None:
            if self.covers_to < self.covers_from:
                raise ValueError("covers_to cannot be before covers_from")
            if (self.covers_to - self.covers_from).days >= MAX_COVER_DAYS:
                raise ValueError(f"an expense can cover at most {MAX_COVER_DAYS} days")
        return self


class ExpenseBulkChanges(PartialUpdate):
    """What "edit together" can set on many expenses at once. Amount, quantity, unit, date and
    currency are per-expense facts, so they are not offered. group_id may be null (move to personal)."""

    not_nullable = frozenset({"category", "subcategory", "description", "shop", "brand"})
    category: Name | None = None
    subcategory: OptionalName | None = None
    description: Text | None = None
    shop: OptionalName | None = None
    brand: OptionalName | None = None
    group_id: int | None = None


class ExpenseBulkFilters(BaseModel):
    """The Expenses page's search & filter, so "everything that matches" can span several pages."""

    scope: str | None = None
    space_ids: str | None = None
    search: str | None = None
    category: str | None = None
    shop: str | None = None
    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    total_only: bool | None = None


# Far above what one person edits at once, but a hard stop on a runaway request.
MAX_BULK_UPDATE = 5000


class ExpenseBulkUpdate(BaseModel):
    ids: list[int] | None = Field(default=None, min_length=1, max_length=MAX_BULK_UPDATE)
    filters: ExpenseBulkFilters | None = None
    changes: ExpenseBulkChanges

    @model_validator(mode="after")
    def _one_target_and_a_change(self):
        if (self.ids is None) == (self.filters is None):
            raise ValueError("send either ids or filters")
        if not self.changes.model_dump(exclude_unset=True):
            raise ValueError("changes must set at least one field")
        return self


class ExpenseBulkCopy(BaseModel):
    """Copy expenses into a space (a trip, say): the ids given, or everything matching a search &
    filter. The copies are new expenses owned by the person copying; the originals are untouched."""

    ids: list[int] | None = Field(default=None, min_length=1, max_length=MAX_BULK_UPDATE)
    filters: ExpenseBulkFilters | None = None
    group_id: int

    @model_validator(mode="after")
    def _one_target(self):
        if (self.ids is None) == (self.filters is None):
            raise ValueError("send either ids or filters")
        return self


class ExpenseBulkCreate(BaseModel):
    items: list[ExpenseCreate] = Field(min_length=1, max_length=1000)
    # Itemising a bill: the bill these line items break down. Once saved the bill is
    # "itemised" and any single "total only" expense it had is replaced by the items.
    bill_id: int | None = None
    # Re-itemising: the bill is already itemised and these items replace its current ones.
    # Without it an already-itemised bill is refused, which protects against double submits.
    replace: bool = False
    # Add by bill: the items are one bill. A bill record is made for them right away, so it shows
    # on the Bills page as itemised (otherwise it is picked up the next time the page loads).
    as_bill: bool = False


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


_FETCH_KEYS = (
    "id", "date", "category", "subcategory", "description", "amount", "quantity", "unit",
    "shop", "brand", "currency", "price_per_unit", "bill_total_only", "recurring_template_id",
    "group_id", "user_id",
)
_FETCH_COLUMNS = tuple(getattr(models.Expense, k) for k in _FETCH_KEYS)


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
    # Plain column rows, not ORM objects: the aggregations only need values, and building
    # an ORM entity per row was the larger half of the cost on big accounts.
    rows = q.with_entities(*_FETCH_COLUMNS).order_by(models.Expense.date, models.Expense.id).all()
    items = [dict(zip(_FETCH_KEYS, r)) for r in rows]
    for item in items:
        item["bill_total_only"] = bool(item["bill_total_only"])
    return items


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


def _apply_list_filters(q, search, category, shop, date_from, date_to, total_only):
    """The Expenses page's search & filter, shared by the list and by "edit everything that matches"."""
    # Case does not matter: "milk" finds what was entered as "Milk" or "MILK".
    if category and category.strip():
        q = q.filter(func.lower(models.Expense.category) == category.strip().lower())
    if shop and shop.strip():
        q = q.filter(func.lower(models.Expense.shop) == shop.strip().lower())
    if date_from:
        q = q.filter(models.Expense.date >= date_from)
    if date_to:
        q = q.filter(models.Expense.date <= date_to)
    if total_only is not None:
        q = q.filter(models.Expense.bill_total_only == total_only)
    if search and search.strip():
        like = like_pattern(search)
        q = q.filter(
            or_(
                models.Expense.description.ilike(like, escape=LIKE_ESCAPE),
                models.Expense.shop.ilike(like, escape=LIKE_ESCAPE),
                models.Expense.brand.ilike(like, escape=LIKE_ESCAPE),
                models.Expense.category.ilike(like, escape=LIKE_ESCAPE),
                models.Expense.subcategory.ilike(like, escape=LIKE_ESCAPE),
            )
        )
    return q


@router.get("/expenses")
def list_expenses(
    scope: str | None = None,
    space_ids: str | None = None,
    search: str | None = None,
    category: str | None = None,
    shop: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    total_only: bool | None = None,
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

    q = _apply_list_filters(q, search, category, shop, date_from, date_to, total_only)

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
            "source_bill_id": r.source_bill_id,
            "bill_total_only": bool(r.bill_total_only),
            "recurring_template_id": r.recurring_template_id,
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
    bill_sync.adopt_after_write(db, user.id)  # file it under a bill
    # Auto-learn any new category/subcategory/unit/shop into the user's taxonomy.
    ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    return expense


@router.post("/expenses/bulk", response_model=list[ExpenseOut], status_code=201)
def create_expenses_bulk(
    payload: ExpenseBulkCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Add several line items from a single bill/receipt in one request.

    With ``bill_id`` the items itemise that bill: they are linked to it, the bill becomes
    "itemised", and the single total-only expense it may have had is removed (replaced by
    the items) in the same transaction, so nothing is double counted. With ``replace`` an
    already-itemised bill is re-itemised: its current items are replaced by the new ones.
    """
    for item in payload.items:
        _require_group_write_access(db, item.group_id, user.id)

    bill = None
    if payload.bill_id is not None:
        # Lock the bill row for this transaction so two simultaneous submissions (including two
        # re-itemisations) are handled one after the other instead of both inserting items.
        bill = (
            db.query(models.PendingBill)
            .filter(models.PendingBill.id == payload.bill_id, models.PendingBill.user_id == user.id)
            .with_for_update()
            .first()
        )
        if bill is None:
            raise HTTPException(status_code=404, detail="Bill not found")
        allowed = ("pending", "total_only", "itemised") if payload.replace else ("pending", "total_only")
        claimed = (
            db.query(models.PendingBill)
            .filter(models.PendingBill.id == bill.id, models.PendingBill.status.in_(allowed))
            .update({"status": "itemised"}, synchronize_session=False)
        )
        if claimed != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="This bill has already been itemised")
        replaced = db.query(models.Expense).filter(
            models.Expense.source_bill_id == bill.id,
            models.Expense.user_id == user.id,
        )
        if not payload.replace:
            # First itemisation: only the single total-only line is replaced.
            replaced = replaced.filter(models.Expense.bill_total_only.is_(True))
        replaced.delete(synchronize_session=False)

    created: list[models.Expense] = []
    for item in payload.items:
        data = item.model_dump()
        data["currency"] = data["currency"] or default_currency_for(db, user.id, item.group_id)
        if bill is not None:
            data["source_bill_id"] = bill.id
        expense = models.Expense(user_id=user.id, **data)
        expense.price_per_unit = _price_per_unit(expense.amount, expense.quantity)
        db.add(expense)
        created.append(expense)
    if bill is not None and bill.origin == bill_sync.ORIGIN_EXPENSES:
        # The user has taken over this bill's items: keep them together as one bill whatever their
        # shop/date, and let its amount follow the new items.
        bill.origin_key = bill_sync.new_explicit_key()
        bill.amount = sum((e.amount for e in created), Decimal("0"))
    elif bill is not None and (bill.amount is None or bill.amount <= 0) and created:
        # A receipt uploaded with nothing filled in (amount 0, named after its file, dated the
        # day it was uploaded): the items you typed are what say what the bill was.
        bill.amount = sum((e.amount for e in created), Decimal("0"))
        if len({e.date for e in created}) == 1:
            bill.date = created[0].date
        if len({e.currency for e in created}) == 1:
            bill.currency = created[0].currency
        shops = {(e.shop or "").strip() for e in created}
        if len(shops) == 1 and next(iter(shops)):
            bill.shop = next(iter(shops))
    elif bill is None and payload.as_bill and created:
        same_day = {e.date for e in created}
        same_currency = {e.currency for e in created}
        if len(same_day) == 1 and len(same_currency) == 1:
            db.flush()
            first = created[0]
            record = models.PendingBill(
                user_id=user.id,
                date=first.date,
                shop=bill_sync.bill_name(first),
                amount=sum((e.amount for e in created), Decimal("0")),
                note="",
                status="itemised",
                possible_duplicate=False,
                currency=first.currency,
                origin=bill_sync.ORIGIN_EXPENSES,
                origin_key=bill_sync.new_explicit_key(),
            )
            db.add(record)
            db.flush()
            for e in created:
                e.source_bill_id = record.id
    db.commit()
    for expense in created:
        db.refresh(expense)
        ensure_options(db, user.id, expense.category, expense.subcategory, expense.unit, expense.shop)
    return created


@router.post("/expenses/bulk-update")
def update_expenses_bulk(
    payload: ExpenseBulkUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Apply the same changes to many expenses at once: the ids given, or everything matching a
    search & filter. All or nothing: one expense the user may not edit stops the whole request, so
    a failure never leaves a half-edited set."""
    data = payload.changes.model_dump(exclude_unset=True)

    if payload.ids is not None:
        ids = list(dict.fromkeys(payload.ids))
        expenses = [_get_visible_or_404(db, i, user.id) for i in ids]
    else:
        f = payload.filters
        q = _visible_expenses_query(db, user.id, f.scope, f.space_ids)
        if q is None:
            return {"updated": 0}
        q = _apply_list_filters(q, f.search, f.category, f.shop, f.date_from, f.date_to, f.total_only)
        if q.count() > MAX_BULK_UPDATE:
            raise HTTPException(status_code=422, detail=f"That is more than {MAX_BULK_UPDATE} expenses; narrow the filters first")
        expenses = q.all()
    if not expenses:
        return {"updated": 0}

    # Check every permission before changing anything.
    for expense in expenses:
        _require_group_write_access(db, expense.group_id, user.id, expense.user_id)
        if "group_id" in data:
            _require_group_write_access(db, data["group_id"], user.id, expense.user_id)

    bills_by_owner: dict[int, set[int]] = {}
    for expense in expenses:
        if expense.source_bill_id is not None and expense.user_id is not None:
            bills_by_owner.setdefault(expense.user_id, set()).add(expense.source_bill_id)
        if "group_id" in data and data["group_id"] != expense.group_id:
            expense.covers_from = expense.covers_to = None  # the days belonged to the old trip
        for field, value in data.items():
            setattr(expense, field, value)
    db.commit()

    for owner_id, bill_ids in bills_by_owner.items():
        # A bill made from expenses follows its items (regrouping if the shop changed).
        bill_sync.sync_user_bills(db, owner_id, bill_ids=sorted(bill_ids))

    seen = {(e.category, e.subcategory, e.unit, e.shop) for e in expenses}
    for category, subcategory, unit, shop in seen:
        ensure_options(db, user.id, category, subcategory, unit, shop)
    return {"updated": len(expenses)}


@router.post("/expenses/bulk-copy")
def copy_expenses_bulk(
    payload: ExpenseBulkCopy,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Copy many expenses into a space, e.g. bank-statement rows into the trip they belong to.

    Reading the originals is enough (they are not changed); writing to the target space is what is
    checked. Rows already in that space are skipped, so a double click can't double them. The copies
    are plain expenses: they are not tied to the original's bill or recurring template. All or
    nothing, like the other bulk actions."""
    if payload.ids is not None:
        ids = list(dict.fromkeys(payload.ids))
        sources = [_get_visible_or_404(db, i, user.id) for i in ids]
    else:
        f = payload.filters
        q = _visible_expenses_query(db, user.id, f.scope, f.space_ids)
        if q is None:
            return {"copied": 0, "skipped": 0}
        q = _apply_list_filters(q, f.search, f.category, f.shop, f.date_from, f.date_to, f.total_only)
        if q.count() > MAX_BULK_UPDATE:
            raise HTTPException(status_code=422, detail=f"That is more than {MAX_BULK_UPDATE} expenses; narrow the filters first")
        sources = q.all()

    _require_group_write_access(db, payload.group_id, user.id)
    to_copy = [e for e in sources if e.group_id != payload.group_id]
    skipped = len(sources) - len(to_copy)

    for e in to_copy:
        db.add(
            models.Expense(
                user_id=user.id,
                date=e.date,
                category=e.category,
                subcategory=e.subcategory,
                description=e.description,
                amount=e.amount,
                quantity=e.quantity,
                unit=e.unit,
                shop=e.shop,
                brand=e.brand,
                currency=e.currency,
                price_per_unit=e.price_per_unit,
                group_id=payload.group_id,
            )
        )
    db.commit()
    return {"copied": len(to_copy), "skipped": skipped}


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expense = _get_visible_or_404(db, expense_id, user.id)
    _require_group_write_access(db, expense.group_id, user.id, expense.user_id)
    linked_bill_id, owner_id = expense.source_bill_id, expense.user_id
    data = payload.model_dump(exclude_unset=True)
    if "group_id" in data:
        _require_group_write_access(db, data["group_id"], user.id, expense.user_id)
        if data["group_id"] != expense.group_id and "covers_from" not in data:
            data["covers_from"] = data["covers_to"] = None  # the days belonged to the old trip
    if data.get("covers_from") is not None:
        target = data["group_id"] if "group_id" in data else expense.group_id
        space = db.get(models.Group, target) if target is not None else None
        if space is None or space.space_type != "trip":
            raise HTTPException(status_code=422, detail="Days can only be set on an expense that is in a trip")
    for field, value in data.items():
        setattr(expense, field, value)
    expense.price_per_unit = _price_per_unit(expense.amount, expense.quantity)
    db.commit()
    if linked_bill_id is not None and owner_id is not None:
        # A bill made from expenses follows its items (amount, and regrouping if shop/date changed).
        bill_sync.sync_user_bills(db, owner_id, bill_ids=[linked_bill_id])
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
    reopen_bill_id = expense.source_bill_id if expense.bill_total_only else None
    linked_bill_id = expense.source_bill_id
    owner_id = expense.user_id
    db.delete(expense)
    if reopen_bill_id is not None:
        # The recorded total is gone, so the bill goes back to "to itemise" rather than
        # claiming a spend that no longer exists.
        db.query(models.PendingBill).filter(
            models.PendingBill.id == reopen_bill_id,
            models.PendingBill.user_id == owner_id,
            models.PendingBill.status == "total_only",
        ).update({"status": "pending"}, synchronize_session=False)
    db.commit()
    if linked_bill_id is not None and owner_id is not None:
        # A bill made from expenses follows its items; it goes away with the last one.
        bill_sync.sync_user_bills(db, owner_id, bill_ids=[linked_bill_id])


@router.get("/expenses/summary")
def expenses_summary(
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    return summary_payload(expenses, unconverted, get_reporting_currency(db, user.id))


def summary_payload(expenses: list[dict], unconverted: int, reporting: str) -> dict:
    """Totals for already-converted expenses (shared with the combined /dashboard endpoint)."""
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
    # Undo the quote our export adds in front of formula-looking text, so a re-import round-trips.
    return None if pd.isna(value) else unescape_formula(value)


@router.post("/expenses/import")
def import_expenses(
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
    raw = read_upload_limited_sync(file, MAX_IMPORT_FILE_BYTES)
    try:
        if name.endswith(".xlsx"):
            ensure_xlsx_within_limits(raw)
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
    # "milk" in the file becomes "Milk" if that is how the user's list spells it, and
    # variants new to the list agree with the first one seen.
    categories = CategoryResolver(list(get_or_create_options(db, user.id).categories or []))

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
            category = categories.resolve(category)
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
    bill_sync.adopt_after_write(db, user.id)
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
    # Free-text columns are neutralised so a shop/item like "=HYPERLINK(...)" cannot run as a
    # formula when the file is opened; numbers and dates are left as real values.
    text = escape_formula
    df = pd.DataFrame(
        [
            {
                "Date": r["date"],
                "Category": text(r["category"]),
                "Subcategory": text(r["subcategory"]),
                "Item": text(r["description"]),
                "Shop": text(r["shop"]),
                "Brand": text(r["brand"]),
                "PricePaid": r["amount"],
                "Quantity": r["quantity"],
                "QuantityUnit": text(r["unit"]),
                "PricePerUnit": r["price_per_unit"],
                "Currency": text(r["currency"]),
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
