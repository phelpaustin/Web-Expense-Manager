"""Full personal backup: everything one account owns, as one zip, and the restore from it.

The zip holds ``backup.json`` plus one file per receipt (``receipts/<bill>``). Bills are kept as
containers: a bill row says which expenses are its items (``bill`` on each expense), so a restore
brings back exactly the same purchases and nothing is regrouped by date and shop.

Not included: Expense Spaces and the expenses filed in them (they belong to several people), the
login itself (restoring needs an account to restore into) and exchange-rate caches.

Restore only fills an account that has no data yet, so it can never mix two histories together or
overwrite anything. Ids are renumbered; ``e|<expense id>`` keys of derived bills are renumbered with them.
"""
import datetime as dt
import io
import json
import zipfile
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import receipt_storage
from app.core.currency import normalize_currency
from app.core.file_validation import detect_receipt_content_type
from app.core.money import MAX_MONEY
from app.db import models

FORMAT = "expense-manager-backup"
VERSION = 1

MAX_BACKUP_BYTES = 150 * 1024 * 1024        # the uploaded zip
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # what it may expand to (zip bombs)
MAX_JSON_BYTES = 120 * 1024 * 1024
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_ENTRIES = 20_000
MAX_ROWS = 300_000

_CHUNK = 1000


class BackupError(ValueError):
    """The file is not a usable backup (shown to the user as is)."""


class AccountNotEmpty(BackupError):
    pass


# ── building ───────────────────────────────────────────────────────────────
def _d(value):
    return value.isoformat() if value is not None else None


def _n(value):
    return str(value) if value is not None else None


def build_backup(db: Session, user: models.User) -> tuple[bytes, dict]:
    """The backup zip for this user and a small summary (counts, what was left out)."""
    uid = user.id
    opts = db.query(models.UserOptions).filter(models.UserOptions.user_id == uid).first()
    expenses = (
        db.query(models.Expense)
        .filter(models.Expense.user_id == uid, models.Expense.group_id.is_(None))
        .order_by(models.Expense.id)
        .all()
    )
    in_spaces = (
        db.query(func.count(models.Expense.id))
        .filter(models.Expense.user_id == uid, models.Expense.group_id.isnot(None))
        .scalar()
    )
    has_items = {e.source_bill_id for e in expenses if e.source_bill_id is not None}
    bills = []
    for b in db.query(models.PendingBill).filter(models.PendingBill.user_id == uid).order_by(models.PendingBill.id):
        # An itemised bill whose items are all in a space has nothing left to hold.
        if b.status == "itemised" and b.id not in has_items:
            continue
        bills.append(b)
    bill_ids = {b.id for b in bills}

    files: dict[str, bytes] = {}
    missing_receipts = 0
    bill_rows = []
    receipts = {r.pending_bill_id: r for r in db.query(models.Receipt).filter(models.Receipt.user_id == uid)}
    store = None
    for b in bills:
        row = {
            "id": b.id, "date": _d(b.date), "shop": b.shop, "amount": _n(b.amount), "note": b.note,
            "status": b.status, "possible_duplicate": bool(b.possible_duplicate), "currency": b.currency,
            "origin": b.origin, "origin_key": b.origin_key, "receipt": None,
        }
        r = receipts.get(b.id)
        if r is not None:
            content = r.data
            if r.storage_key:
                store = store or receipt_storage.get_store()
                try:
                    content = store.get(r.storage_key) if store is not None else None
                except receipt_storage.ReceiptStorageError:
                    content = None
            if content:
                name = f"receipts/{b.id}"
                files[name] = bytes(content)
                row["receipt"] = {"file": name, "filename": r.filename, "content_type": r.content_type}
            else:
                missing_receipts += 1
        bill_rows.append(row)

    goals = []
    for g in db.query(models.SavingsGoal).filter(models.SavingsGoal.user_id == uid).order_by(models.SavingsGoal.id):
        contribs = (
            db.query(models.SavingsContribution)
            .filter(models.SavingsContribution.goal_id == g.id, models.SavingsContribution.user_id == uid)
            .order_by(models.SavingsContribution.id)
        )
        goals.append({
            "name": g.name, "target_amount": _n(g.target_amount), "currency": g.currency,
            "target_date": _d(g.target_date), "note": g.note,
            "contributions": [{"date": _d(c.date), "amount": _n(c.amount), "note": c.note} for c in contribs],
        })

    templates = db.query(models.RecurringTemplate).filter(models.RecurringTemplate.user_id == uid).order_by(models.RecurringTemplate.id).all()
    data = {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "options": None if opts is None else {
            "categories": opts.categories, "subcategories": opts.subcategories, "units": opts.units,
            "shops": opts.shops, "base_currency": opts.base_currency, "display_currency": opts.display_currency,
            "alert_digest_enabled": bool(opts.alert_digest_enabled), "budget_period": opts.budget_period,
            "budget_rollover": bool(opts.budget_rollover),
        },
        "budgets": [
            {"category": b.category, "amount": _n(b.amount), "currency": b.currency}
            for b in db.query(models.Budget).filter(models.Budget.user_id == uid).order_by(models.Budget.id)
        ],
        "income": [
            {"date": _d(i.date), "amount": _n(i.amount), "source": i.source, "note": i.note, "currency": i.currency}
            for i in db.query(models.Income).filter(models.Income.user_id == uid).order_by(models.Income.id)
        ],
        "recurring": [
            {"id": t.id, "item": t.item, "category": t.category, "amount": _n(t.amount), "frequency": t.frequency,
             "note": t.note, "auto_post": bool(t.auto_post), "last_applied": _d(t.last_applied),
             "schedule_anchor": _d(t.schedule_anchor), "currency": t.currency}
            for t in templates
        ],
        "bills": bill_rows,
        "expenses": [
            {"id": e.id, "date": _d(e.date), "category": e.category, "subcategory": e.subcategory,
             "description": e.description, "amount": _n(e.amount), "quantity": e.quantity, "unit": e.unit,
             "shop": e.shop, "brand": e.brand, "currency": e.currency, "price_per_unit": _n(e.price_per_unit),
             "bill": e.source_bill_id if e.source_bill_id in bill_ids else None,
             "bill_total_only": bool(e.bill_total_only), "recurring": e.recurring_template_id,
             "covers_from": _d(e.covers_from), "covers_to": _d(e.covers_to)}
            for e in expenses
        ],
        "savings_goals": goals,
        "aliases": [
            {"kind": a.kind, "alias": a.alias, "alias_key": a.alias_key, "canonical": a.canonical}
            for a in db.query(models.NameAlias).filter(models.NameAlias.user_id == uid)
        ],
        "import_profiles": [
            {"name": p.name, "signature": p.signature, "mapping": p.mapping}
            for p in db.query(models.ImportProfile).filter(models.ImportProfile.user_id == uid)
        ],
        "dismissed_duplicates": [
            {"key": x.key, "day": _d(x.day), "count": x.count}
            for x in db.query(models.DismissedDuplicate).filter(models.DismissedDuplicate.user_id == uid)
        ],
    }
    summary = {
        "expenses": len(data["expenses"]), "bills": len(bill_rows), "receipts": len(files),
        "income": len(data["income"]), "budgets": len(data["budgets"]), "recurring": len(templates),
        "savings_goals": len(goals), "left_out_space_expenses": in_spaces, "missing_receipts": missing_receipts,
    }
    data["summary"] = summary

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup.json", json.dumps(data, ensure_ascii=False))
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue(), summary


# ── reading and validating ─────────────────────────────────────────────────
def _text(max_length):
    return Field(default="", max_length=max_length)


def _money(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("not a number") from exc
    if not d.is_finite() or abs(d) > MAX_MONEY:
        raise ValueError("amount out of range")
    return d


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Money(_Row):
    @field_validator("amount", "price_per_unit", "target_amount", mode="before", check_fields=False)
    @classmethod
    def _amount(cls, v):
        return _money(v)

    @field_validator("currency", mode="before", check_fields=False)
    @classmethod
    def _currency(cls, v):
        return normalize_currency(str(v))


class OptionsIn(_Row):
    categories: list[str] = Field(default_factory=list, max_length=500)
    subcategories: dict[str, list[str]] = Field(default_factory=dict)
    units: list[str] = Field(default_factory=list, max_length=500)
    shops: list[str] = Field(default_factory=list, max_length=5000)
    base_currency: str = "SEK"
    display_currency: str | None = None
    alert_digest_enabled: bool = True
    budget_period: str = Field(default="Monthly", max_length=20)
    budget_rollover: bool = False

    @field_validator("base_currency", "display_currency", mode="before")
    @classmethod
    def _cur(cls, v):
        return None if v in (None, "") else normalize_currency(str(v))


class BudgetIn(_Money):
    category: str = Field(min_length=1, max_length=200)
    amount: Decimal
    currency: str


class IncomeIn(_Money):
    date: dt.date
    amount: Decimal
    source: str = _text(200)
    note: str = _text(1000)
    currency: str


class RecurringIn(_Money):
    id: int
    item: str = Field(min_length=1, max_length=200)
    category: str = _text(200)
    amount: Decimal
    frequency: str = Field(default="Monthly", max_length=30)
    note: str = _text(1000)
    auto_post: bool = False
    last_applied: dt.date | None = None
    schedule_anchor: dt.date | None = None
    currency: str


class ReceiptIn(_Row):
    file: str
    filename: str = Field(default="receipt", max_length=200)


class BillIn(_Money):
    id: int
    date: dt.date
    shop: str = _text(200)
    amount: Decimal
    note: str = _text(1000)
    status: str = Field(pattern=r"^(pending|total_only|itemised)$")
    possible_duplicate: bool = False
    currency: str
    origin: str | None = Field(default=None, pattern=r"^expenses$")
    origin_key: str | None = Field(default=None, max_length=300)
    receipt: ReceiptIn | None = None


class ExpenseIn(_Money):
    id: int
    date: dt.date
    category: str = Field(min_length=1, max_length=200)
    subcategory: str = _text(200)
    description: str = _text(1000)
    amount: Decimal
    quantity: float = Field(default=1.0, ge=0, le=1e9)
    unit: str = Field(default="Count", max_length=200)
    shop: str = _text(200)
    brand: str = _text(200)
    currency: str
    price_per_unit: Decimal = Decimal("0")
    bill: int | None = None
    bill_total_only: bool = False
    recurring: int | None = None
    covers_from: dt.date | None = None
    covers_to: dt.date | None = None


class ContributionIn(_Money):
    date: dt.date
    amount: Decimal
    note: str = _text(1000)


class GoalIn(_Money):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal
    currency: str
    target_date: dt.date | None = None
    note: str = _text(1000)
    contributions: list[ContributionIn] = Field(default_factory=list, max_length=20_000)


class AliasIn(_Row):
    kind: str = Field(pattern=r"^(item|shop)$")
    alias: str = Field(min_length=1, max_length=200)
    alias_key: str = Field(min_length=1, max_length=200)
    canonical: str = Field(min_length=1, max_length=200)


class ProfileIn(_Row):
    name: str = Field(min_length=1, max_length=80)
    signature: str = Field(min_length=1, max_length=64)
    mapping: dict | list


class DismissedIn(_Row):
    key: str = Field(min_length=1, max_length=64)
    day: dt.date
    count: int = Field(ge=0, le=1_000_000)


class BackupIn(_Row):
    options: OptionsIn | None = None
    budgets: list[BudgetIn] = Field(default_factory=list)
    income: list[IncomeIn] = Field(default_factory=list)
    recurring: list[RecurringIn] = Field(default_factory=list)
    bills: list[BillIn] = Field(default_factory=list)
    expenses: list[ExpenseIn] = Field(default_factory=list)
    savings_goals: list[GoalIn] = Field(default_factory=list)
    aliases: list[AliasIn] = Field(default_factory=list)
    import_profiles: list[ProfileIn] = Field(default_factory=list)
    dismissed_duplicates: list[DismissedIn] = Field(default_factory=list)


def read_backup(raw: bytes) -> tuple[BackupIn, dict[str, bytes]]:
    """Open and validate an uploaded backup. Raises BackupError with a message fit to show."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise BackupError("This is not a backup file from this app (it is not a zip).") from exc
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise BackupError("This backup is too large to restore.")
        names = {i.filename: i for i in infos}
        info = names.get("backup.json")
        if info is None or info.file_size > MAX_JSON_BYTES:
            raise BackupError("This is not a backup file from this app (backup.json is missing or too large).")
        try:
            data = json.loads(z.read(info))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BackupError("The backup's data could not be read.") from exc
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise BackupError("This is not a backup file from this app.")
        if data.get("version") != VERSION:
            raise BackupError("This backup was made by a different version of the app and cannot be restored.")
        for key in ("expenses", "bills", "income", "budgets", "recurring", "savings_goals"):
            rows = data.get(key) or []
            if not isinstance(rows, list):
                raise BackupError(f"The backup's {key} are not in the expected form.")
        if sum(len(data.get(k) or []) for k in ("expenses", "bills", "income")) > MAX_ROWS:
            raise BackupError("This backup has too many rows to restore.")
        try:
            parsed = BackupIn.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise BackupError(f"The backup has an invalid value at {where}: {first['msg']}") from exc

        files: dict[str, bytes] = {}
        for b in parsed.bills:
            if b.receipt is None:
                continue
            ri = names.get(b.receipt.file)
            if ri is None or ri.file_size > MAX_RECEIPT_BYTES:
                raise BackupError(f"The receipt for bill {b.id} is missing from the backup or too large.")
            files[b.receipt.file] = z.read(ri)
    _check_links(parsed)
    return parsed, files


def _check_links(p: BackupIn) -> None:
    bill_ids = {b.id for b in p.bills}
    if len(bill_ids) != len(p.bills):
        raise BackupError("The backup lists the same bill twice.")
    if len({e.id for e in p.expenses}) != len(p.expenses):
        raise BackupError("The backup lists the same expense twice.")
    for e in p.expenses:
        if e.bill is not None and e.bill not in bill_ids:
            raise BackupError(f"Expense {e.id} points at a bill that is not in the backup.")
    cats = [b.category for b in p.budgets]
    if len(set(cats)) != len(cats):
        raise BackupError("The backup lists the same budget twice.")
    keys = [b.origin_key for b in p.bills if b.origin_key]
    if len(set(keys)) != len(keys):
        raise BackupError("The backup lists the same derived bill twice.")


# ── restoring ──────────────────────────────────────────────────────────────
def _has_data(db: Session, uid: int) -> bool:
    for model in (models.Expense, models.PendingBill, models.Budget, models.Income, models.RecurringTemplate, models.SavingsGoal):
        if db.query(model.id).filter(model.user_id == uid).first() is not None:
            return True
    return False


def restore_backup(db: Session, user: models.User, parsed: BackupIn, files: dict[str, bytes], store_receipt) -> dict:
    """Write the backup into an empty account. Caller commits (and rolls back on an exception).

    ``store_receipt(db, user_id, bill_id, filename, content_type, data)`` files one receipt
    (see app.api.bills._store_receipt, which honours object storage).
    """
    uid = user.id
    if _has_data(db, uid):
        raise AccountNotEmpty(
            "Restoring works on an account that has no expenses, bills, budgets, income, recurring items or "
            "savings goals yet. Register a new account and restore there."
        )

    if parsed.options is not None:
        from app.api.options import get_or_create_options

        o = get_or_create_options(db, uid)
        for field, value in parsed.options.model_dump().items():
            setattr(o, field, value)

    for b in parsed.budgets:
        db.add(models.Budget(user_id=uid, category=b.category, amount=b.amount, currency=b.currency))
    for i in parsed.income:
        db.add(models.Income(user_id=uid, date=i.date, amount=i.amount, source=i.source, note=i.note, currency=i.currency))

    template_ids: dict[int, int] = {}
    for t in parsed.recurring:
        row = models.RecurringTemplate(
            user_id=uid, item=t.item, category=t.category, amount=t.amount, frequency=t.frequency, note=t.note,
            auto_post=t.auto_post, last_applied=t.last_applied, schedule_anchor=t.schedule_anchor, currency=t.currency,
        )
        db.add(row)
        db.flush()
        template_ids[t.id] = row.id

    bill_rows: dict[int, models.PendingBill] = {}
    for b in parsed.bills:
        row = models.PendingBill(
            user_id=uid, date=b.date, shop=b.shop, amount=b.amount, note=b.note, status=b.status,
            possible_duplicate=b.possible_duplicate, currency=b.currency, origin=b.origin,
            origin_key=None if b.origin_key and b.origin_key.startswith("e|") else b.origin_key,
        )
        db.add(row)
        bill_rows[b.id] = row
    db.flush()

    new_expense_id: dict[int, int] = {}
    for part in _parts(parsed.expenses):
        pairs = []
        for e in part:
            row = models.Expense(
                user_id=uid, date=e.date, category=e.category, subcategory=e.subcategory, description=e.description,
                amount=e.amount, quantity=e.quantity, unit=e.unit, shop=e.shop, brand=e.brand, currency=e.currency,
                price_per_unit=e.price_per_unit, group_id=None,
                source_bill_id=bill_rows[e.bill].id if e.bill is not None else None,
                bill_total_only=e.bill_total_only, recurring_template_id=template_ids.get(e.recurring),
                covers_from=e.covers_from, covers_to=e.covers_to,
            )
            db.add(row)
            pairs.append((e.id, row))
        db.flush()
        for old, row in pairs:
            new_expense_id[old] = row.id

    # A one-expense purchase is keyed by its expense's id, which just changed.
    for b in parsed.bills:
        if b.origin_key and b.origin_key.startswith("e|"):
            try:
                old = int(b.origin_key[2:])
            except ValueError:
                continue
            if old in new_expense_id:
                bill_rows[b.id].origin_key = f"e|{new_expense_id[old]}"
    db.flush()

    for b in parsed.bills:
        if b.receipt is not None:
            data = files[b.receipt.file]
            try:
                content_type = detect_receipt_content_type(data)
            except ValueError as exc:
                raise BackupError(f"The receipt for bill {b.id} is not a PDF, JPEG or PNG.") from exc
            store_receipt(db, uid, bill_rows[b.id].id, b.receipt.filename, content_type, data)

    for g in parsed.savings_goals:
        goal = models.SavingsGoal(
            user_id=uid, name=g.name, target_amount=g.target_amount, currency=g.currency,
            target_date=g.target_date, note=g.note,
        )
        db.add(goal)
        db.flush()
        for c in g.contributions:
            db.add(models.SavingsContribution(goal_id=goal.id, user_id=uid, date=c.date, amount=c.amount, note=c.note))

    seen_alias = set()
    for a in parsed.aliases:
        if (a.kind, a.alias_key) in seen_alias:
            continue
        seen_alias.add((a.kind, a.alias_key))
        db.add(models.NameAlias(user_id=uid, kind=a.kind, alias=a.alias, alias_key=a.alias_key, canonical=a.canonical))
    seen_profile = set()
    for p in parsed.import_profiles:
        if p.name in seen_profile:
            continue
        seen_profile.add(p.name)
        db.add(models.ImportProfile(user_id=uid, name=p.name, signature=p.signature, mapping=p.mapping))
    seen_dismissed = set()
    for x in parsed.dismissed_duplicates:
        if x.key in seen_dismissed:
            continue
        seen_dismissed.add(x.key)
        db.add(models.DismissedDuplicate(user_id=uid, key=x.key, day=x.day, count=x.count))
    db.flush()

    return {
        "expenses": len(parsed.expenses), "bills": len(parsed.bills),
        "receipts": sum(1 for b in parsed.bills if b.receipt is not None),
        "income": len(parsed.income), "budgets": len(parsed.budgets), "recurring": len(parsed.recurring),
        "savings_goals": len(parsed.savings_goals),
    }


def _parts(rows, size=_CHUNK):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]
