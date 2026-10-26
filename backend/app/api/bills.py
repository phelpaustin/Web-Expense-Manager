import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.options import (
    default_currency_for,
    ensure_options,
    get_or_create_options,
)
from app.core.fx import normalize_convertible_currency
from app.core.file_validation import detect_receipt_content_type
from app.core.file_upload import content_disposition, read_upload_limited_sync, safe_filename
from app.core.import_limits import MAX_IMPORT_FILE_BYTES
from app.core.validation import MAX_NAME, Name, Text
from app.api import bill_sync
from app.core import receipt_storage
from app.api.expenses import ExpenseOut
from app.db.database import get_db
from app.core.money import MAX_MONEY
from app.db import models
from app.logic.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

_MAX_RECEIPT_BYTES = MAX_IMPORT_FILE_BYTES


def _valid_currency(value: str | None) -> str | None:
    return normalize_convertible_currency(value) if value is not None else None


class PendingCreate(BaseModel):
    date: datetime.date
    shop: Name
    amount: Decimal = Field(gt=0, le=MAX_MONEY)
    note: Text = ""
    currency: str | None = None  # None = the user's base currency

    check_currency = field_validator("currency")(lambda cls, v: _valid_currency(v))


def _pending_or_404(db: Session, bill_id: int, user_id: int) -> models.PendingBill:
    b = db.get(models.PendingBill, bill_id)
    if b is None or b.user_id != user_id:
        raise HTTPException(status_code=404, detail="Pending bill not found")
    return b


STATUS_PENDING = "pending"        # to itemise: no expense yet
STATUS_TOTAL_ONLY = "total_only"  # recorded as one expense for the whole amount; can still be itemised
STATUS_ITEMISED = "itemised"      # broken down into its line items
DEFAULT_BILL_CATEGORY = "Bills"
_FROM_EXPENSES_MESSAGE = "Made from expenses you entered: delete those expenses to remove it"

_SORTS = {
    "date_desc": (models.PendingBill.date.desc(), models.PendingBill.id.desc()),
    "date_asc": (models.PendingBill.date.asc(), models.PendingBill.id.asc()),
    "amount_desc": (models.PendingBill.amount.desc(), models.PendingBill.id.desc()),
    "amount_asc": (models.PendingBill.amount.asc(), models.PendingBill.id.asc()),
    "shop": (models.PendingBill.shop.asc(), models.PendingBill.date.desc()),
}


def _serialize_pending(b: models.PendingBill, has_receipt: bool, item_count: int = 0) -> dict:
    return {
        "id": b.id,
        "date": b.date.isoformat(),
        "shop": b.shop,
        "amount": b.amount,
        "currency": b.currency,
        "note": b.note,
        "status": b.status,
        "has_receipt": has_receipt,
        "possible_duplicate": bool(b.possible_duplicate),
        # Expenses created from this bill: 1 for a total-only bill, N for an itemised one.
        "item_count": item_count,
        # Made from expenses entered some other way; it follows them and is removed with them.
        "from_expenses": b.origin == bill_sync.ORIGIN_EXPENSES,
    }


def _receipt_flags(db: Session, user_id: int, bill_ids: list[int]) -> set[int]:
    if not bill_ids:
        return set()
    return {
        r.pending_bill_id
        for r in db.query(models.Receipt.pending_bill_id).filter(
            models.Receipt.user_id == user_id, models.Receipt.pending_bill_id.in_(bill_ids)
        )
    }


def _item_counts(db: Session, user_id: int, bill_ids: list[int]) -> dict[int, int]:
    if not bill_ids:
        return {}
    rows = (
        db.query(models.Expense.source_bill_id, func.count(models.Expense.id))
        .filter(models.Expense.user_id == user_id, models.Expense.source_bill_id.in_(bill_ids))
        .group_by(models.Expense.source_bill_id)
        .all()
    )
    return {bill_id: n for bill_id, n in rows}


def _serialize_one(db: Session, user_id: int, b: models.PendingBill) -> dict:
    return _serialize_pending(
        b,
        b.id in _receipt_flags(db, user_id, [b.id]),
        _item_counts(db, user_id, [b.id]).get(b.id, 0),
    )


# ── Recording a bill's total as spending ──────────────────────
def _record_total(
    db: Session,
    user: models.User,
    bill: models.PendingBill,
    category: str | None = None,
    amount: Decimal | None = None,
) -> models.Expense:
    """Create the single total-only expense for a pending bill and claim the bill.

    The bill moves pending -> total_only atomically, so a double click or a second tab
    can't record it twice. Caller commits.
    """
    final_amount = amount if amount is not None else bill.amount
    if final_amount is None or final_amount <= 0:
        raise HTTPException(status_code=400, detail="Enter an amount greater than zero to record this bill")
    claimed = (
        db.query(models.PendingBill)
        .filter(
            models.PendingBill.id == bill.id,
            models.PendingBill.user_id == user.id,
            models.PendingBill.status == STATUS_PENDING,
        )
        .update({"status": STATUS_TOTAL_ONLY, "amount": final_amount}, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This bill has already been recorded or itemised")
    expense = models.Expense(
        user_id=user.id,
        date=bill.date,
        category=(category or "").strip() or DEFAULT_BILL_CATEGORY,
        description=bill.shop,
        shop=bill.shop,
        amount=final_amount,
        currency=bill.currency,
        price_per_unit=final_amount,
        source_bill_id=bill.id,
        bill_total_only=True,
    )
    db.add(expense)
    return expense


def _auto_record(db: Session, user: models.User, bills: list[models.PendingBill]) -> int:
    """Record new bills as total-only expenses when the user's setting is on.

    Bills flagged as possible duplicates are left for review (recording them could
    double count), and so are bills with no readable amount. Caller commits.
    """
    if not get_or_create_options(db, user.id).count_bills_as_spending:
        return 0
    recorded = 0
    for b in bills:
        if b.possible_duplicate or b.amount is None or b.amount <= 0 or b.status != STATUS_PENDING:
            continue
        _record_total(db, user, b)
        recorded += 1
    return recorded


def _learn_default_category(db: Session, user_id: int) -> None:
    ensure_options(db, user_id, DEFAULT_BILL_CATEGORY, "", "")


# ── List (one list for every status; paginated) ───────────────
@router.get("/bills")
def list_bills(
    status: str = Query(default=STATUS_PENDING, pattern=r"^(pending|total_only|itemised|all)$"),
    q: str | None = Query(default=None, max_length=100),
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    sort: str = Query(default="date_desc", pattern=r"^(date_desc|date_asc|amount_desc|amount_asc|shop)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Bills of every status with filters, sorting and pagination.

    ``counts`` always covers every status (for the tab badges) under the same search and
    date filters, so the tabs show how much is waiting without loading it.
    """
    base = db.query(models.PendingBill).filter(models.PendingBill.user_id == user.id)
    if date_from:
        base = base.filter(models.PendingBill.date >= date_from)
    if date_to:
        base = base.filter(models.PendingBill.date <= date_to)
    if q and q.strip():
        like = like_pattern(q)
        base = base.filter(
            or_(models.PendingBill.shop.ilike(like, escape=LIKE_ESCAPE), models.PendingBill.note.ilike(like, escape=LIKE_ESCAPE))
        )

    counts = {STATUS_PENDING: 0, STATUS_TOTAL_ONLY: 0, STATUS_ITEMISED: 0}
    for st, n in base.with_entities(models.PendingBill.status, func.count(models.PendingBill.id)).group_by(
        models.PendingBill.status
    ):
        if st in counts:
            counts[st] = n
    counts["all"] = sum(counts.values())

    rows_q = base if status == "all" else base.filter(models.PendingBill.status == status)
    total = counts["all"] if status == "all" else counts[status]
    bills = rows_q.order_by(*_SORTS[sort]).offset((page - 1) * page_size).limit(page_size).all()
    ids = [b.id for b in bills]
    has_receipt = _receipt_flags(db, user.id, ids)
    item_counts = _item_counts(db, user.id, ids)
    return {
        "items": [_serialize_pending(b, b.id in has_receipt, item_counts.get(b.id, 0)) for b in bills],
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": counts,
        # Read-only: true when expenses are not yet filed under bills (or a derived bill is out of
        # date). The page then calls POST /bills/sync once and reloads; a GET never writes.
        "needs_sync": bill_sync.needs_sync(db, user.id),
    }


@router.post("/bills/sync")
def sync_bills(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """File every expense under a bill and bring derived bills up to date. Idempotent."""
    return {"changed": bill_sync.sync_user_bills(db, user.id)}


@router.get("/bills/{bill_id}")
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return _serialize_one(db, user.id, _pending_or_404(db, bill_id, user.id))


@router.get("/bills/{bill_id}/items", response_model=list[ExpenseOut])
def list_bill_items(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The line items an itemised bill currently has (for editing them). A bill recorded as a
    total only has no items; its single total line is not included."""
    bill = _pending_or_404(db, bill_id, user.id)
    return (
        db.query(models.Expense)
        .filter(
            models.Expense.source_bill_id == bill.id,
            models.Expense.user_id == user.id,
            models.Expense.bill_total_only.is_(False),
        )
        .order_by(models.Expense.id)
        .all()
    )


@router.post("/pending-bills", status_code=201)
def create_pending(
    payload: PendingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Add a bill by hand. With "count bills as spending" on it is recorded as a total right away."""
    data = payload.model_dump()
    data["currency"] = data["currency"] or default_currency_for(db, user.id)
    b = models.PendingBill(user_id=user.id, **data)
    db.add(b)
    db.flush()
    recorded = _auto_record(db, user, [b])
    db.commit()
    if recorded:
        _learn_default_category(db, user.id)
    db.refresh(b)
    return _serialize_one(db, user.id, b)


def _store_receipt(db: Session, user_id: int, bill_id: int, filename: str | None, content_type: str, data: bytes) -> str | None:
    """Attach the file to the bill. Caller commits, then passes the returned key (the object this
    receipt replaced, if any) to ``receipt_storage.delete_objects``.

    With object storage configured the file is uploaded first and the row keeps only its key; an
    upload that fails stops the request before anything is written to the database.
    """
    store = receipt_storage.get_store()
    key = None
    if store is not None:
        key = receipt_storage.new_key(user_id, bill_id)
        try:
            store.put(key, data, content_type)
        except receipt_storage.ReceiptStorageError as exc:
            raise HTTPException(status_code=503, detail="Receipt storage is unavailable right now. Please try again.") from exc
    stored = None if key else data
    existing = db.query(models.Receipt).filter(models.Receipt.pending_bill_id == bill_id).first()
    if existing:
        replaced = existing.storage_key
        existing.filename = safe_filename(filename, "receipt")
        existing.content_type = content_type
        existing.data = stored
        existing.storage_key = key
        return replaced
    db.add(
        models.Receipt(
            user_id=user_id,
            pending_bill_id=bill_id,
            filename=safe_filename(filename, "receipt"),
            content_type=content_type,
            data=stored,
            storage_key=key,
        )
    )
    return None


@router.post("/pending-bills/upload")
def upload_pending(
    response: Response,
    file: UploadFile = File(...),
    shop: str = Form("", max_length=MAX_NAME),
    amount: Decimal = Form(Decimal("0"), ge=0, le=MAX_MONEY),
    attach_to: int | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Upload a receipt (PDF/photo), to itemise whenever you like.

    The receipt is only stored: nothing is read from it. Everything is filled in by you.

    * ``attach_to`` puts the receipt on an existing bill (e.g. one from a bank statement).
    * Otherwise a new bill is created, dated today, named after the file unless ``shop`` is
      given, with the amount you give (default 0 = not known yet). It waits under "To itemise";
      nothing counts as spending until you record its total or itemise it.
    """
    data = read_upload_limited_sync(file, _MAX_RECEIPT_BYTES, status_code=400)
    try:
        content_type = detect_receipt_content_type(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if attach_to is not None:
        bill = _pending_or_404(db, attach_to, user.id)
        replaced = _store_receipt(db, user.id, bill.id, file.filename, content_type, data)
        db.commit()
        receipt_storage.delete_objects([replaced])
        response.status_code = 200
        return {"result": "attached", "bill": _serialize_one(db, user.id, bill)}

    b = models.PendingBill(
        user_id=user.id,
        date=datetime.date.today(),
        shop=(shop.strip() or safe_filename(file.filename, "Uploaded bill")),
        amount=amount,
        currency=default_currency_for(db, user.id),
        note="",
        status=STATUS_PENDING,
    )
    db.add(b)
    db.flush()
    _store_receipt(db, user.id, b.id, file.filename, content_type, data)
    recorded = _auto_record(db, user, [b])
    db.commit()
    if recorded:
        _learn_default_category(db, user.id)
    db.refresh(b)
    response.status_code = 201
    return {"result": "created", "bill": _serialize_one(db, user.id, b)}


@router.post("/pending-bills/{bill_id}/dismiss-duplicate")
def dismiss_duplicate(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Acknowledge a flagged bill isn't actually a duplicate, clearing the flag."""
    bill = _pending_or_404(db, bill_id, user.id)
    bill.possible_duplicate = False
    db.commit()
    return _serialize_one(db, user.id, bill)


def _receipt_keys(db: Session, bill_ids: list[int]) -> list[str]:
    """Object-storage keys of the receipts on these bills (none for receipts kept in the database)."""
    if not bill_ids:
        return []
    return [
        k
        for (k,) in db.query(models.Receipt.storage_key).filter(
            models.Receipt.pending_bill_id.in_(bill_ids), models.Receipt.storage_key.isnot(None)
        )
    ]


def _delete_bill_record(db: Session, bill: models.PendingBill) -> list[str]:
    """Remove a bill (and its receipt). Expenses made from it are kept, just unlinked.

    Returns the receipt's object-storage keys; delete them after committing."""
    keys = _receipt_keys(db, [bill.id])
    db.query(models.Receipt).filter(models.Receipt.pending_bill_id == bill.id).delete()
    db.query(models.Expense).filter(models.Expense.source_bill_id == bill.id).update(
        {"source_bill_id": None}, synchronize_session=False
    )
    db.delete(bill)
    return keys


@router.delete("/pending-bills/{bill_id}", status_code=204)
def delete_pending(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    bill = _pending_or_404(db, bill_id, user.id)
    if bill.status == STATUS_TOTAL_ONLY:
        raise HTTPException(status_code=409, detail="Undo the recorded total before deleting this bill")
    if bill.origin == bill_sync.ORIGIN_EXPENSES:
        raise HTTPException(status_code=409, detail=_FROM_EXPENSES_MESSAGE)
    keys = _delete_bill_record(db, bill)
    db.commit()
    receipt_storage.delete_objects(keys)
    bill_sync.adopt_after_write(db, user.id)  # its expenses are kept: file them under a derived bill


class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class BulkRecordIn(BulkIds):
    category: str | None = Field(default=None, max_length=100)


@router.post("/bills/bulk-delete")
def bulk_delete_bills(
    payload: BulkIds,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Delete several bills. Bills recorded as a total must be undone first."""
    deleted, skipped = 0, []
    keys: list[str] = []
    for bill in db.query(models.PendingBill).filter(
        models.PendingBill.user_id == user.id, models.PendingBill.id.in_(payload.ids)
    ):
        if bill.status == STATUS_TOTAL_ONLY:
            skipped.append({"id": bill.id, "reason": "Undo the recorded total first"})
            continue
        if bill.origin == bill_sync.ORIGIN_EXPENSES:
            skipped.append({"id": bill.id, "reason": _FROM_EXPENSES_MESSAGE})
            continue
        keys += _delete_bill_record(db, bill)
        deleted += 1
    db.commit()
    receipt_storage.delete_objects(keys)
    if deleted:
        bill_sync.adopt_after_write(db, user.id)
    return {"deleted": deleted, "skipped": skipped}


# ── Record total / undo ───────────────────────────────────────
class RecordTotalIn(BaseModel):
    category: str | None = Field(default=None, max_length=100)
    # For a bill whose amount couldn't be read: the amount to record (also saved on the bill).
    amount: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY)


@router.post("/bills/record-total")
def record_totals_bulk(
    payload: BulkRecordIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Record the whole amount of several bills as spending (itemise them later if you like).

    Bills flagged as possible duplicates are skipped: review them first, since recording
    them could double count.
    """
    recorded, skipped = 0, []
    bills = (
        db.query(models.PendingBill)
        .filter(models.PendingBill.user_id == user.id, models.PendingBill.id.in_(payload.ids))
        .order_by(models.PendingBill.id)
        .all()
    )
    found = {b.id for b in bills}
    skipped += [{"id": i, "reason": "Bill not found"} for i in payload.ids if i not in found]
    for b in bills:
        if b.status != STATUS_PENDING:
            skipped.append({"id": b.id, "reason": "Already recorded or itemised"})
        elif b.possible_duplicate:
            skipped.append({"id": b.id, "reason": "Possible duplicate: review it first"})
        elif b.amount is None or b.amount <= 0:
            skipped.append({"id": b.id, "reason": "No amount to record"})
        else:
            _record_total(db, user, b, payload.category)
            recorded += 1
    db.commit()
    if recorded:
        _learn_default_category(db, user.id)
        if payload.category:
            ensure_options(db, user.id, payload.category.strip(), "", "")
    return {"recorded": recorded, "skipped": skipped}


@router.post("/bills/{bill_id}/record-total")
def record_total(
    bill_id: int,
    payload: RecordTotalIn | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Record one bill's whole amount as a single expense. It counts towards budgets
    straight away, stays linked to the bill, and can be itemised later."""
    bill = _pending_or_404(db, bill_id, user.id)
    payload = payload or RecordTotalIn()
    _record_total(db, user, bill, payload.category, payload.amount)
    db.commit()
    ensure_options(db, user.id, (payload.category or DEFAULT_BILL_CATEGORY).strip(), "", "")
    db.refresh(bill)
    return _serialize_one(db, user.id, bill)


@router.post("/bills/{bill_id}/revert-to-total")
def revert_to_total(
    bill_id: int,
    payload: RecordTotalIn | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Turn an itemised bill back into a single total: its items are replaced by one expense for
    the bill's full amount, and the bill returns to "total only" (so it can be itemised again)."""
    payload = payload or RecordTotalIn()
    bill = (
        db.query(models.PendingBill)
        .filter(models.PendingBill.id == bill_id, models.PendingBill.user_id == user.id)
        .with_for_update()
        .first()
    )
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status != STATUS_ITEMISED:
        raise HTTPException(status_code=409, detail="Only an itemised bill can be turned back into a total")
    if bill.amount is None or bill.amount <= 0:
        raise HTTPException(status_code=400, detail="This bill has no amount to record as a total")
    claimed = (
        db.query(models.PendingBill)
        .filter(models.PendingBill.id == bill.id, models.PendingBill.status == STATUS_ITEMISED)
        .update({"status": STATUS_TOTAL_ONLY}, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Only an itemised bill can be turned back into a total")
    db.query(models.Expense).filter(
        models.Expense.source_bill_id == bill.id, models.Expense.user_id == user.id
    ).delete(synchronize_session=False)
    category = (payload.category or "").strip() or DEFAULT_BILL_CATEGORY
    # Once the user turns a bill into a total themselves it is theirs, not tracked from its items.
    bill.origin, bill.origin_key = None, None
    db.add(
        models.Expense(
            user_id=user.id,
            date=bill.date,
            category=category,
            description=bill.shop,
            shop=bill.shop,
            amount=bill.amount,
            currency=bill.currency,
            price_per_unit=bill.amount,
            source_bill_id=bill.id,
            bill_total_only=True,
        )
    )
    db.commit()
    ensure_options(db, user.id, category, "", "")
    db.refresh(bill)
    return _serialize_one(db, user.id, bill)


@router.post("/bills/{bill_id}/undo")
def undo_record_total(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Take a recorded total back: the one-line expense is removed and the bill returns to
    "to itemise"."""
    bill = _pending_or_404(db, bill_id, user.id)
    claimed = (
        db.query(models.PendingBill)
        .filter(models.PendingBill.id == bill.id, models.PendingBill.status == STATUS_TOTAL_ONLY)
        .update({"status": STATUS_PENDING}, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Only a bill recorded as a total can be undone")
    db.query(models.Expense).filter(
        models.Expense.source_bill_id == bill.id,
        models.Expense.bill_total_only.is_(True),
        models.Expense.user_id == user.id,
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(bill)
    return _serialize_one(db, user.id, bill)


# ── Receipts (attached to pending bills) ──────────────────────
@router.post("/pending-bills/{bill_id}/receipt")
def upload_receipt(
    bill_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Attach (or replace) a receipt on a bill of any status."""
    bill = _pending_or_404(db, bill_id, user.id)
    data = read_upload_limited_sync(file, _MAX_RECEIPT_BYTES, status_code=400)
    try:
        content_type = detect_receipt_content_type(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    replaced = _store_receipt(db, user.id, bill.id, file.filename, content_type, data)
    db.commit()
    receipt_storage.delete_objects([replaced])
    return {"uploaded": True}


@router.get("/pending-bills/{bill_id}/receipt")
def get_receipt(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    bill = _pending_or_404(db, bill_id, user.id)
    r = db.query(models.Receipt).filter(models.Receipt.pending_bill_id == bill.id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="No receipt")
    content = r.data
    if r.storage_key:
        store = receipt_storage.get_store()
        if store is None:
            raise HTTPException(status_code=503, detail="Receipt storage is not configured on this server")
        try:
            content = store.get(r.storage_key)
        except receipt_storage.ReceiptFileMissing as exc:
            raise HTTPException(status_code=404, detail="This receipt's file is missing from storage") from exc
        except receipt_storage.ReceiptStorageError as exc:
            raise HTTPException(status_code=503, detail="Receipt storage is unavailable right now. Please try again.") from exc
    return Response(
        content=content,
        media_type=r.content_type,
        headers={
            "Content-Disposition": content_disposition(safe_filename(r.filename, "receipt")),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/pending-bills/{bill_id}/receipt", status_code=204)
def delete_receipt(
    bill_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    bill = _pending_or_404(db, bill_id, user.id)
    keys = _receipt_keys(db, [bill.id])
    db.query(models.Receipt).filter(models.Receipt.pending_bill_id == bill.id).delete()
    db.commit()
    receipt_storage.delete_objects(keys)
