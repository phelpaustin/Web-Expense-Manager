"""Keep every expense represented on the Bills page, however it was entered.

Bills made from a bank statement, a receipt or by hand already link to their expenses. Expenses
entered any other way (the Expenses page, an import, a recurring item, "Add by bill") have no bill,
so they were invisible on the Bills page. This module fixes that by *adopting* them into
"derived" bills (``origin == 'expenses'``):

* Grouping matches the Expenses page's own bill view: expenses with a shop share one bill per
  (date, shop, currency, space); an expense with no shop is a bill by itself.
* Derived bills are always "itemised" (their expenses are real, categorised lines) and their
  amount is the sum of their items. They disappear with their last item, unless a receipt is
  attached, in which case they become an ordinary bill to itemise so the receipt is not lost.
* Bills the user created or imported are never regrouped or changed here.

It runs when the Bills or Expenses page loads and after an expense is edited or deleted, so
existing expenses are picked up the first time and anything added later by any route follows.
It is idempotent, and a unique index (user, origin_key) makes concurrent runs safe: the loser
of a race simply retries and finds the other's bills.
"""
import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models

ORIGIN_EXPENSES = "expenses"
EXPLICIT_PREFIX = "b|"
_CHUNK = 400  # keep IN (...) lists well under every database's parameter limit
_RETRIES = 3


def implicit_key(e: models.Expense) -> str:
    """Which derived bill an expense belongs to, by its own fields."""
    shop = (e.shop or "").strip().lower()
    if shop:
        return f"s|{e.date.isoformat()}|{shop}|{e.currency}|{e.group_id or 0}"
    return f"e|{e.id}"  # no shop: not enough to say it belongs with anything else


def bill_name(e: models.Expense) -> str:
    return (e.shop or "").strip() or (e.description or "").strip() or (e.category or "").strip() or "Expense"


def new_explicit_key() -> str:
    """Key for a derived bill whose items are chosen by the user (Add by bill, re-itemise): its
    items stay together whatever their shop/date, so it is never regrouped."""
    return f"{EXPLICIT_PREFIX}{uuid.uuid4().hex}"


def is_explicit(key: str | None) -> bool:
    return bool(key) and key.startswith(EXPLICIT_PREFIX)


def _chunks(seq, size=_CHUNK):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def has_unlinked(db: Session, user_id: int) -> bool:
    return (
        db.query(models.Expense.id)
        .filter(
            models.Expense.user_id == user_id,
            models.Expense.source_bill_id.is_(None),
            models.Expense.bill_total_only.is_(False),
        )
        .first()
        is not None
    )


def _set_amounts(db: Session, bills: dict[int, models.PendingBill]) -> None:
    """amount = the sum of the bill's items."""
    from sqlalchemy import func

    for part in _chunks(bills):
        sums = dict(
            db.query(models.Expense.source_bill_id, func.sum(models.Expense.amount))
            .filter(models.Expense.source_bill_id.in_(part))
            .group_by(models.Expense.source_bill_id)
            .all()
        )
        for bill_id in part:
            total = Decimal(str(sums.get(bill_id) or 0))
            if bills[bill_id].amount != total:
                bills[bill_id].amount = total


def _adopt(db: Session, user_id: int) -> bool:
    """Put every expense that is not in a bill into a derived bill. Caller commits."""
    rows = (
        db.query(models.Expense)
        .filter(
            models.Expense.user_id == user_id,
            models.Expense.source_bill_id.is_(None),
            models.Expense.bill_total_only.is_(False),
        )
        .all()
    )
    if not rows:
        return False
    groups: dict[str, list[models.Expense]] = defaultdict(list)
    for e in rows:
        groups[implicit_key(e)].append(e)

    bills: dict[str, models.PendingBill] = {}
    for part in _chunks(groups):
        for b in db.query(models.PendingBill).filter(
            models.PendingBill.user_id == user_id, models.PendingBill.origin_key.in_(part)
        ):
            bills[b.origin_key] = b
    for key, exps in groups.items():
        if key in bills:
            continue
        first = exps[0]
        bill = models.PendingBill(
            user_id=user_id,
            date=first.date,
            shop=bill_name(first),
            amount=Decimal("0"),
            note="",
            status="itemised",
            possible_duplicate=False,
            currency=first.currency,
            origin=ORIGIN_EXPENSES,
            origin_key=key,
        )
        db.add(bill)
        bills[key] = bill
    db.flush()  # gives the new bills their ids

    touched: dict[int, models.PendingBill] = {}
    for key, exps in groups.items():
        bill = bills[key]
        touched[bill.id] = bill
        for e in exps:
            e.source_bill_id = bill.id
    db.flush()
    _set_amounts(db, touched)
    return True


def _reconcile(db: Session, user_id: int, bill_ids: list[int] | None = None) -> bool:
    """Bring derived bills back in line with their expenses. Caller commits.

    * Items that no longer match their (implicit) bill, because their date, shop, currency or space
      was edited, are detached; adoption then files them in the right bill.
    * amount follows the items.
    * A bill left with no items is removed, or kept as a bill to itemise if it has a receipt.
    """
    q = db.query(models.PendingBill).filter(
        models.PendingBill.user_id == user_id,
        models.PendingBill.origin == ORIGIN_EXPENSES,
        models.PendingBill.status == "itemised",
    )
    if bill_ids is not None:
        if not bill_ids:
            return False
        q = q.filter(models.PendingBill.id.in_(bill_ids))
    bills = q.all()
    if not bills:
        return False

    ids = [b.id for b in bills]
    items_by_bill: dict[int, list[models.Expense]] = defaultdict(list)
    with_receipt: set[int] = set()
    for part in _chunks(ids):
        for e in db.query(models.Expense).filter(
            models.Expense.source_bill_id.in_(part), models.Expense.user_id == user_id
        ):
            items_by_bill[e.source_bill_id].append(e)
        with_receipt |= {
            r.pending_bill_id
            for r in db.query(models.Receipt.pending_bill_id).filter(models.Receipt.pending_bill_id.in_(part))
        }

    changed = False
    for b in bills:
        items = items_by_bill.get(b.id, [])
        if b.origin_key and not is_explicit(b.origin_key):
            keep = []
            for e in items:
                if implicit_key(e) == b.origin_key and not e.bill_total_only:
                    keep.append(e)
                else:
                    e.source_bill_id = None
                    changed = True
            items = keep
        if not items:
            if b.id in with_receipt:
                b.status, b.origin, b.origin_key = "pending", None, None  # keep the receipt
            else:
                db.delete(b)
            changed = True
            continue
        total = sum((e.amount for e in items), Decimal("0"))
        if b.amount != total:
            b.amount = total
            changed = True
    return changed


def sync_user_bills(db: Session, user_id: int, bill_ids: list[int] | None = None, reconcile: bool = True) -> bool:
    """Reconcile derived bills (all of them, or just ``bill_ids``) and adopt unlinked expenses.

    Commits only when something changed. Returns whether anything did.
    """
    last_error: IntegrityError | None = None
    for _ in range(_RETRIES):
        try:
            changed = _reconcile(db, user_id, bill_ids) if reconcile else False
            # Sessions here don't autoflush: write the reconcile's deletes and detaches before adopting,
            # otherwise adoption would still see the deleted bills and the detached expenses as linked.
            db.flush()
            changed = _adopt(db, user_id) or changed
            if changed:
                db.commit()
            return changed
        except IntegrityError as exc:  # a concurrent request adopted the same expenses first
            db.rollback()
            last_error = exc
    raise last_error  # pragma: no cover - three losses in a row is not realistic


def adopt_if_needed(db: Session, user_id: int) -> None:
    """Cheap guard for hot paths (listing expenses): adopt only when something is unlinked."""
    if has_unlinked(db, user_id):
        sync_user_bills(db, user_id, reconcile=False)
