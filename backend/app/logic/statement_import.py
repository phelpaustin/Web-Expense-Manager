"""Reading bank statements: find the table, guess the columns, decide expense or income.

Pure functions (no database, no web framework). A statement is read in three steps:

1. ``read_grid`` turns a CSV/XLSX upload into rows of text.
2. ``analyse`` finds the header row and guesses a ``Mapping`` (which column is the date,
   the amount ...). The person can correct any of it.
3. ``classify`` applies a mapping to every row and says, per row, whether it is an
   expense, income, a duplicate, to be skipped, or an error, and why.

The mapping is the whole contract: a person edits it, an AI suggestion fills it in, and the
same ``classify`` call produces the preview and the final import, so what is previewed is
exactly what is saved.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.parsing import decode_text, parse_amount
from app.logic.categorizer import categorize_by_rules

MAX_GRID_ROWS = 10_000
MAX_COLUMNS = 60
MAX_CELL_CHARS = 1_000
HEADER_SCAN_ROWS = 30
UNCATEGORIZED = "Uncategorized"

Sign = Literal["negative_is_expense", "positive_is_expense"]
DateOrder = Literal["auto", "dayfirst", "monthfirst", "ymd"]
Kind = Literal["expense", "income"]


# ── Reading the file ──────────────────────────────────────────────────────

def _clean_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return text[:MAX_CELL_CHARS]


def grid_from_csv(raw: bytes) -> list[list[str]]:
    """Rows of text from a CSV, tolerating a preamble of ragged lines above the table."""
    text = decode_text(raw)
    try:
        delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ";" if text[:8192].count(";") > text[:8192].count(",") else ","
    rows: list[list[str]] = []
    for record in csv.reader(io.StringIO(text), delimiter=delimiter, skipinitialspace=True):
        rows.append([_clean_cell(c) for c in record[:MAX_COLUMNS]])
        if len(rows) > MAX_GRID_ROWS + HEADER_SCAN_ROWS:
            break
    return rows


def grid_from_dataframe(df) -> list[list[str]]:
    """Rows of text from a header-less DataFrame (an .xlsx read with header=None)."""
    rows = []
    for record in df.itertuples(index=False, name=None):
        rows.append([_clean_cell(c) for c in record[:MAX_COLUMNS]])
    return rows


def _width(grid: list[list[str]]) -> int:
    return max((len(r) for r in grid), default=0)


# ── Dates ─────────────────────────────────────────────────────────────────

_YMD = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")
_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def _make_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _year(y: int) -> int:
    return y + 2000 if y < 100 else y


def _split_date(text: str):
    """(kind, a, b, c) for the first three numbers of a date-looking cell, else None."""
    text = text.strip()
    if m := _YMD.match(text):
        return "ymd", int(m[1]), int(m[2]), int(m[3])
    if m := _COMPACT.match(text):
        return "ymd", int(m[1]), int(m[2]), int(m[3])
    if m := _DMY.match(text):
        return "dmy", int(m[1]), int(m[2]), _year(int(m[3]))
    return None


def parse_date(text: str, order: DateOrder = "auto") -> date | None:
    """A date from a cell, or None. ``order`` only matters for day/month written first."""
    parts = _split_date(text)
    if parts is None:
        return None
    kind, a, b, c = parts
    if kind == "ymd":
        return _make_date(a, b, c)
    if order == "monthfirst":
        return _make_date(c, a, b)
    return _make_date(c, b, a)  # day first is the default (and "auto" has been resolved by now)


def detect_date_order(cells: list[str]) -> tuple[DateOrder, bool]:
    """(order, ambiguous). Looks at every date: a first number above 12 proves day-first, a second
    number above 12 proves month-first. With no proof either way it assumes day first and says so."""
    day_first = month_first = False
    seen_dmy = False
    for cell in cells:
        parts = _split_date(cell)
        if not parts:
            continue
        if parts[0] == "ymd":
            continue
        seen_dmy = True
        _, a, b, _c = parts
        if a > 12:
            day_first = True
        if b > 12:
            month_first = True
    if not seen_dmy:
        return "ymd", False
    if month_first and not day_first:
        return "monthfirst", False
    if day_first and not month_first:
        return "dayfirst", False
    return "dayfirst", not (day_first or month_first)


def looks_like_date(text: str) -> bool:
    parts = _split_date(text)
    if not parts:
        return False
    if parts[0] == "ymd":
        return _make_date(parts[1], parts[2], parts[3]) is not None
    return 1 <= parts[1] <= 31 and 1 <= parts[2] <= 31


def looks_like_amount(text: str) -> bool:
    if not text or looks_like_date(text):
        return False
    try:
        parse_amount(text)
    except (ValueError, ArithmeticError, TypeError):
        return False
    return any(ch.isdigit() for ch in text)


# ── The mapping ───────────────────────────────────────────────────────────

RuleAction = Literal["skip", "expense", "income"]
MAX_RULES = 30


class Rule(BaseModel):
    """"When a row's text contains X: leave it out / make it an expense / income / file it under Y".

    This is what a typed instruction such as "skip internal transfers" or "Swish from Anna is
    income" becomes. It is plain data, so the AI never runs anything: it can only propose rules,
    and the preview shows exactly what they do before anything is saved.
    """

    contains: str = Field(min_length=1, max_length=80)
    action: RuleAction | None = None
    category: str | None = Field(default=None, max_length=80)

    @field_validator("contains", mode="before")
    @classmethod
    def _strip_contains(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("category", mode="before")
    @classmethod
    def _blank_category(cls, value):
        return None if value is None or (isinstance(value, str) and not value.strip()) else (value.strip() if isinstance(value, str) else value)

    @model_validator(mode="after")
    def _does_something(self):
        if not self.contains:
            raise ValueError("a rule needs some text to look for")
        if self.action is None and not self.category:
            raise ValueError("a rule needs an action or a category")
        return self

    def label(self) -> str:
        what = [self.action] if self.action else []
        if self.category:
            what.append(f"category {self.category}")
        return f"“{self.contains}” → {', '.join(what)}"


class Mapping(BaseModel):
    """Which column means what. Column values are the labels from ``Table.labels``."""

    header_row: int = Field(default=0, ge=0, le=HEADER_SCAN_ROWS * 4)
    date: str | None = None
    description: str | None = None
    # Either one signed column ...
    amount: str | None = None
    sign: Sign = "negative_is_expense"
    # ... or separate money-out / money-in columns (always positive numbers) ...
    debit: str | None = None
    credit: str | None = None
    # ... or a column saying which way each row goes ("DR"/"CR", "Debit"/"Credit" ...).
    direction: str | None = None
    category: str | None = None
    shop: str | None = None
    currency_column: str | None = None
    currency: str | None = Field(default=None, max_length=10)  # applied to every row when set
    date_order: DateOrder = "auto"
    # Rows whose description contains any of these (case-insensitive) are left out.
    skip_containing: list[str] = Field(default_factory=list, max_length=30)
    # "When the text contains ..." rules, first match wins per aspect (skip beats everything).
    rules: list[Rule] = Field(default_factory=list, max_length=MAX_RULES)
    # Which kinds to import; lets someone take only the expenses (or only the income).
    include_expenses: bool = True
    include_income: bool = True

    @field_validator("skip_containing")
    @classmethod
    def _clean_skip(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip()[:80] for v in value if isinstance(v, str) and v.strip()]
        return cleaned[:30]

    @field_validator(
        "date", "description", "amount", "debit", "credit", "direction", "category", "shop", "currency_column",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value):
        return None if value is None or (isinstance(value, str) and not value.strip()) else value

    def column_fields(self) -> dict[str, str]:
        names = ("date", "description", "amount", "debit", "credit", "direction", "category", "shop", "currency_column")
        return {n: getattr(self, n) for n in names if getattr(self, n)}


@dataclass
class Table:
    header_row: int
    labels: list[str]
    rows: list[list[str]]  # data rows only, padded to len(labels)
    first_line: int  # 1-based line number in the file of rows[0]

    def index(self, label: str | None) -> int | None:
        if label is None:
            return None
        try:
            return self.labels.index(label)
        except ValueError:
            return None


def build_table(grid: list[list[str]], header_row: int) -> Table:
    """Cut the grid at ``header_row``: that row names the columns, rows below are data."""
    if header_row >= len(grid):
        return Table(header_row, [], [], header_row + 2)
    width = max((len(r) for r in grid[header_row:]), default=0)
    raw = grid[header_row] + [""] * (width - len(grid[header_row]))
    labels: list[str] = []
    seen: Counter = Counter()
    for i, name in enumerate(raw):
        base = name.strip() or f"Column {i + 1}"
        seen[base] += 1
        labels.append(base if seen[base] == 1 else f"{base} ({seen[base]})")
    rows = [r + [""] * (width - len(r)) for r in grid[header_row + 1 :]]
    return Table(header_row, labels, rows, header_row + 2)


# ── Guessing ──────────────────────────────────────────────────────────────

# Header words for each role, in English, Swedish, German, Spanish, French, Dutch, Norwegian, Danish.
_NAMES = {
    "date": [
        "date", "booking date", "transaction date", "posting date", "value date", "datum", "bokföringsdag",
        "bokforingsdag", "transaktionsdag", "transaktionsdatum", "valutadatum", "buchungstag", "buchungsdatum",
        "valuta", "fecha", "fecha operación", "date de comptabilisation", "date opération", "dato", "bokført",
    ],
    "description": [
        "description", "details", "narrative", "memo", "text", "reference", "transaction", "payee", "merchant",
        "name", "beskrivning", "mottagare", "avsändare", "meddelande", "referens", "verwendungszweck",
        "buchungstext", "empfänger", "concepto", "descripción", "libellé", "omschrijving", "beschrijving",
        "tekst", "beskrivelse", "transaktion", "specifikation",
    ],
    "amount": ["amount", "belopp", "betrag", "importe", "montant", "bedrag", "beløp", "value", "sum", "summa"],
    "debit": ["debit", "money out", "withdrawal", "withdrawals", "paid out", "debet", "uttag", "utgift", "soll", "cargo", "débit", "af", "ut"],
    "credit": ["credit", "money in", "deposit", "deposits", "paid in", "kredit", "insättning", "inkomst", "haben", "abono", "crédit", "bij", "inn"],
    "direction": ["type", "dr/cr", "debit/credit", "direction", "typ", "transaction type", "sort"],
    "balance": ["balance", "saldo", "running balance", "kontostand", "solde"],
    "currency": ["currency", "valuta", "währung", "moneda", "devise", "valuuta", "ccy"],
    "category": ["category", "kategori", "kategorie", "categoría", "catégorie", "categorie"],
    "shop": ["shop", "store", "butik", "merchant name", "vendor", "händler"],
}


def header_signature(labels: list[str]) -> str:
    """A fingerprint of a statement's column layout, so the same bank's next export is recognised
    and its saved mapping applied. Order and case of the headers count; their values do not."""
    import hashlib

    joined = "\x1f".join(_norm(label) for label in labels if _norm(label))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def _column(table: Table, i: int) -> list[str]:
    return [r[i] for r in table.rows if i < len(r) and r[i]]


def _header_role(label: str) -> str | None:
    n = _norm(label)
    for role in ("balance", "debit", "credit", "amount", "date", "currency", "category", "shop", "direction", "description"):
        if n in _NAMES[role]:
            return role
    for role in ("balance", "debit", "credit", "amount", "date", "description"):
        if any(len(w) > 3 and w in n for w in _NAMES[role]):
            return role
    return None


def find_header_row(grid: list[list[str]]) -> int:
    """The first row that reads like column names: several text cells, no numbers or dates, with
    transaction rows (a date cell) just below it. Falls back to row 0."""
    for i, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        cells = [c for c in row if c]
        if len(cells) < 2:
            continue
        if any(looks_like_date(c) or looks_like_amount(c) for c in cells):
            continue
        below = grid[i + 1 : i + 5]
        if any(any(looks_like_date(c) for c in r) for r in below):
            return i
    for i, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        if sum(1 for c in row if c) >= 2 and not any(looks_like_date(c) for c in row):
            return i
    return 0


@dataclass
class Analysis:
    table: Table
    mapping: Mapping
    notes: list[str] = field(default_factory=list)


def _share(cells: list[str], test) -> float:
    return sum(1 for c in cells if test(c)) / len(cells) if cells else 0.0


def guess_mapping(table: Table) -> tuple[Mapping, list[str]]:
    notes: list[str] = []
    roles: dict[str, str] = {}
    by_role: dict[str, list[int]] = defaultdict(list)
    for i, label in enumerate(table.labels):
        role = _header_role(label)
        if role:
            by_role[role].append(i)

    def pick(role: str, test=None, min_share: float = 0.5) -> int | None:
        for i in by_role.get(role, []):
            cells = _column(table, i)
            if test is None or _share(cells, test) >= min_share or not cells:
                return i
        return None

    date_i = pick("date", looks_like_date)
    if date_i is None:  # no helpful header: the column most cells of which are dates
        best = max(range(len(table.labels)), key=lambda i: _share(_column(table, i), looks_like_date), default=None)
        if best is not None and _share(_column(table, best), looks_like_date) >= 0.6:
            date_i = best
            notes.append(f"Took “{table.labels[best]}” as the date because its values are dates.")
    used = {date_i}

    debit_i = pick("debit", looks_like_amount)
    credit_i = pick("credit", looks_like_amount)
    amount_i = pick("amount", looks_like_amount)
    if amount_i is None and not (debit_i is not None and credit_i is not None):
        numeric = [
            i for i in range(len(table.labels))
            if i not in used and i not in by_role.get("balance", []) and _share(_column(table, i), looks_like_amount) >= 0.6
        ]
        if numeric:
            amount_i = numeric[0]
            notes.append(f"Took “{table.labels[amount_i]}” as the amount because its values are numbers.")
    if debit_i is not None and credit_i is not None and debit_i != credit_i:
        amount_i = None  # money-out and money-in columns beat a single column
    else:
        debit_i = credit_i = None
    used |= {amount_i, debit_i, credit_i}

    desc_i = pick("description")
    if desc_i is None or desc_i in used:
        text_cols = [
            i for i in range(len(table.labels))
            if i not in used and i not in by_role.get("balance", [])
            and _share(_column(table, i), lambda c: not looks_like_amount(c) and not looks_like_date(c)) >= 0.6
        ]
        if text_cols:
            desc_i = max(text_cols, key=lambda i: sum(len(c) for c in _column(table, i)))
            notes.append(f"Took “{table.labels[desc_i]}” as the description because it holds the longest text.")
        else:
            desc_i = None
    used.add(desc_i)

    cur_i = pick("currency", lambda c: len(c.strip()) == 3 and c.strip().isalpha())
    cat_i = pick("category")
    shop_i = pick("shop")
    dir_i = pick("direction")
    if dir_i is not None and (dir_i in used or amount_i is None and debit_i is not None):
        dir_i = None
    if dir_i is not None:
        values = {c.strip().lower() for c in _column(table, dir_i)}
        if len(values) > 6:  # a free-text column, not a debit/credit marker
            dir_i = None

    cells = _column(table, date_i) if date_i is not None else []
    order, ambiguous = detect_date_order(cells)
    if ambiguous:
        notes.append("Every date could be day/month or month/day; assuming day first. Check the preview.")

    sign: Sign = "negative_is_expense"
    if amount_i is not None and dir_i is None:
        values = []
        for c in _column(table, amount_i):
            try:
                values.append(parse_amount(c))
            except (ValueError, ArithmeticError):
                pass
        negatives = sum(1 for v in values if v < 0)
        if values and negatives == 0:
            sign = "positive_is_expense"
            notes.append("No negative amounts found, so positive amounts are treated as expenses (typical for credit cards). Switch it if your file marks money in as positive.")

    def label(i):
        return table.labels[i] if i is not None else None

    mapping = Mapping(
        header_row=table.header_row, date=label(date_i), description=label(desc_i), amount=label(amount_i),
        sign=sign, debit=label(debit_i), credit=label(credit_i), direction=label(dir_i), category=label(cat_i),
        shop=label(shop_i), currency_column=label(cur_i), date_order=order,
    )
    del roles
    return mapping, notes


def analyse(grid: list[list[str]]) -> Analysis:
    header_row = find_header_row(grid)
    table = build_table(grid, header_row)
    mapping, notes = guess_mapping(table)
    if header_row:
        notes.insert(0, f"Skipped {header_row} line(s) above the column names.")
    return Analysis(table, mapping, notes)


def mapping_problems(mapping: Mapping, table: Table) -> list[str]:
    """What stops this mapping from being used (empty list = usable)."""
    problems = []
    for name, label in mapping.column_fields().items():
        if label not in table.labels:
            problems.append(f"The {name} column “{label}” is not in the file.")
    if not mapping.date:
        problems.append("Choose the date column.")
    if not (mapping.amount or (mapping.debit and mapping.credit)):
        problems.append("Choose the amount column, or both a money-out and a money-in column.")
    if mapping.amount and (mapping.debit or mapping.credit):
        problems.append("Use either one amount column or money-out/money-in columns, not both.")
    if bool(mapping.debit) != bool(mapping.credit):
        problems.append("Money-out and money-in columns go together: choose both or neither.")
    return problems


# ── Applying a mapping ────────────────────────────────────────────────────

_OUT_WORDS = {"d", "dr", "debit", "debet", "withdrawal", "out", "uttag", "soll", "expense", "purchase", "payment"}
_IN_WORDS = {"c", "cr", "credit", "kredit", "deposit", "in", "insättning", "haben", "income", "refund"}


def _direction_kind(text: str) -> Kind | None:
    word = text.strip().lower()
    if word in _OUT_WORDS or word.startswith(("debit", "withdraw")):
        return "expense"
    if word in _IN_WORDS or word.startswith(("credit", "deposit")):
        return "income"
    return None


@dataclass
class Row:
    line: int
    date: date | None = None
    description: str = ""
    shop: str = ""
    amount: Decimal | None = None  # always positive
    currency: str = ""
    kind: Kind | None = None
    category: str = ""
    subcategory: str = ""
    status: Literal["new", "duplicate", "skipped", "error"] = "new"
    reason: str = ""
    overridden: bool = False
    rule: str = ""  # the rule that changed this row, so the preview can say why

    def as_dict(self) -> dict:
        return {
            "line": self.line,
            "date": self.date.isoformat() if self.date else "",
            "description": self.description,
            "shop": self.shop,
            "amount": str(self.amount) if self.amount is not None else "",
            "currency": self.currency,
            "kind": self.kind,
            "category": self.category,
            "subcategory": self.subcategory,
            "status": self.status,
            "reason": self.reason,
            "overridden": self.overridden,
            "rule": self.rule,
        }


class HistoryIndex:
    """What the person already calls things, so a bank's "ICA MAXI 4711" lands in the category
    they used for it last time. Built once per import, looked up per row."""

    def __init__(self, expenses: list[dict] | None = None):
        counts: dict[str, Counter] = defaultdict(Counter)
        for e in expenses or []:
            cat = str(e.get("category") or "").strip()
            if not cat or cat.lower() == UNCATEGORIZED.lower():
                continue
            sub = str(e.get("subcategory") or "").strip()
            for key in {str(e.get("shop") or "").strip().lower(), str(e.get("description") or "").strip().lower()}:
                if key:
                    counts[key][(cat, sub)] += 1
        self._best = {k: c.most_common(1)[0][0] for k, c in counts.items()}

    def lookup(self, *texts: str) -> tuple[str, str] | None:
        for text in texts:
            hit = self._best.get(text.strip().lower())
            if hit:
                return hit
        return None


def suggest_category(history: HistoryIndex, description: str, shop: str) -> tuple[str, str, str]:
    """(category, subcategory, how). History beats keyword rules; neither means Uncategorized."""
    hit = history.lookup(shop, description)
    if hit:
        return hit[0], hit[1], "history"
    by_rule = categorize_by_rules(description, shop)
    if by_rule:
        return by_rule, "", "rules"
    return UNCATEGORIZED, "", "none"


def _apply_rules(rules: list[Rule], description: str, shop: str):
    """(skip_rule, kind_rule, category_rule) for a row: the first rule of each sort that matches."""
    text = f"{description} {shop}".lower()
    skip = kind = category = None
    for rule in rules:
        if rule.contains.lower() not in text:
            continue
        if rule.action == "skip":
            skip = skip or rule
        elif rule.action and kind is None:
            kind = rule
        if rule.category and category is None:
            category = rule
    return skip, kind, category


def _cell(row: list[str], i: int | None) -> str:
    return row[i] if i is not None and i < len(row) else ""


def _kind_and_amount(mapping: Mapping, table: Table, row: list[str]) -> tuple[Kind, Decimal] | str:
    """(kind, positive amount), or a short reason the row cannot be used."""
    if mapping.debit and mapping.credit:
        d_raw, c_raw = _cell(row, table.index(mapping.debit)), _cell(row, table.index(mapping.credit))
        try:
            d = parse_amount(d_raw) if d_raw else Decimal(0)
            c = parse_amount(c_raw) if c_raw else Decimal(0)
        except (ValueError, ArithmeticError):
            return "Amount is not a number"
        if d == 0 and c == 0:
            return "No amount"
        if d != 0 and c != 0:
            return "Both money-out and money-in are filled in"
        return ("expense", abs(d)) if d != 0 else ("income", abs(c))

    raw = _cell(row, table.index(mapping.amount))
    if not raw:
        return "No amount"
    try:
        value = parse_amount(raw)
    except (ValueError, ArithmeticError):
        return "Amount is not a number"
    if value == 0:
        return "Zero amount"
    if mapping.direction:
        kind = _direction_kind(_cell(row, table.index(mapping.direction)))
        if kind is None:
            return "Could not tell money in from money out"
        return kind, abs(value)
    negative = value < 0
    if mapping.sign == "negative_is_expense":
        return ("expense" if negative else "income"), abs(value)
    return ("income" if negative else "expense"), abs(value)


def classify(
    table: Table,
    mapping: Mapping,
    *,
    default_currency: str,
    normalize_currency,
    max_amount: Decimal,
    history: HistoryIndex | None = None,
    existing_expenses: list[dict] | None = None,
    existing_income: list[dict] | None = None,
    overrides: dict[int, str] | None = None,
    category_overrides: dict[int, str] | None = None,
) -> list[Row]:
    """Turn every data row into a ``Row`` with a kind, a status and a reason.

    ``normalize_currency`` is passed in (it needs the FX module) and must raise ValueError for an
    unsupported code. ``overrides`` maps a file line number to "expense", "income" or "skip";
    ``category_overrides`` maps a line to the category the person chose for it.

    Duplicates are counted, not just detected: if the database already holds one coffee for that
    day and the file lists two, one is new. Re-importing a statement therefore adds nothing, while
    two identical purchases in one statement are both kept.
    """
    history = history or HistoryIndex()
    overrides = overrides or {}
    category_overrides = category_overrides or {}
    skips = [s.lower() for s in mapping.skip_containing]
    idx = {name: table.index(label) for name, label in mapping.column_fields().items()}

    have_expense: Counter = Counter()
    for e in existing_expenses or []:
        have_expense[(str(e["date"]), str(e.get("description") or "").strip().lower(), Decimal(str(e["amount"])), e.get("currency") or "")] += 1
    have_income: Counter = Counter()
    for r in existing_income or []:
        have_income[(str(r["date"]), str(r.get("source") or "").strip().lower(), Decimal(str(r["amount"])), r.get("currency") or "")] += 1
    seen: Counter = Counter()

    order = mapping.date_order
    if order == "auto":
        order, _ = detect_date_order([_cell(r, idx.get("date")) for r in table.rows])

    out: list[Row] = []
    for n, cells in enumerate(table.rows):
        line = table.first_line + n
        if not any(cells):
            continue
        row = Row(line=line)
        out.append(row)

        raw_date = _cell(cells, idx.get("date"))
        description = _cell(cells, idx.get("description")).strip()
        row.description = description
        row.shop = _cell(cells, idx.get("shop")).strip()

        if overrides.get(line) == "skip":
            row.status, row.reason, row.overridden = "skipped", "Left out by you", True
            continue
        if not raw_date and not _cell(cells, idx.get("amount")) and not _cell(cells, idx.get("debit")) and not _cell(cells, idx.get("credit")):
            row.status, row.reason = "skipped", "Not a transaction"
            continue
        when = parse_date(raw_date, order)
        if when is None:
            row.status, row.reason = "skipped" if not raw_date else "error", "Not a transaction" if not raw_date else "Could not read the date"
            continue
        row.date = when
        lowered = description.lower()
        if any(s in lowered for s in skips):
            row.status, row.reason = "skipped", "Matches a text you chose to skip"
            continue

        rule_skip, rule_kind, rule_category = _apply_rules(mapping.rules, description, row.shop)
        if rule_skip:
            row.status, row.reason, row.rule = "skipped", f"Rule: {rule_skip.label()}", rule_skip.label()
            continue

        decided = _kind_and_amount(mapping, table, cells)
        if isinstance(decided, str):
            row.status, row.reason = ("skipped" if decided in {"No amount", "Zero amount"} else "error"), decided
            continue
        row.kind, row.amount = decided
        if overrides.get(line) in ("expense", "income"):
            if overrides[line] != row.kind:
                row.kind, row.overridden = overrides[line], True
        elif rule_kind and rule_kind.action != row.kind:
            row.kind, row.rule = rule_kind.action, rule_kind.label()
        if row.amount > max_amount:
            row.status, row.reason = "error", "Amount is too large"
            continue

        code = mapping.currency or _cell(cells, idx.get("currency_column")) or default_currency
        try:
            row.currency = normalize_currency(code)
        except ValueError:
            row.status, row.reason = "error", f"Unsupported currency “{code}”"
            continue

        if (row.kind == "expense" and not mapping.include_expenses) or (row.kind == "income" and not mapping.include_income):
            row.status, row.reason = "skipped", f"{row.kind.capitalize()} rows are switched off"
            continue

        if not row.description:
            row.description = row.shop or ("Income" if row.kind == "income" else "Bank transaction")
        if row.kind == "expense":
            provided = (category_overrides.get(line) or _cell(cells, idx.get("category"))).strip()
            if category_overrides.get(line):
                row.category = provided
            elif rule_category:
                row.category, row.rule = rule_category.category, row.rule or rule_category.label()
            elif provided:
                row.category = provided
            else:
                row.category, row.subcategory, _how = suggest_category(history, row.description, row.shop)
        key = (str(when), row.description.strip().lower(), row.amount, row.currency)
        pool = have_expense if row.kind == "expense" else have_income
        seen[(row.kind, key)] += 1
        if seen[(row.kind, key)] <= pool[key]:
            row.status, row.reason = "duplicate", "Already in your records"
    return out


def summarise(rows: list[Row]) -> dict:
    """Counts and totals for the preview header."""
    by_status = Counter(r.status for r in rows)
    new_expense = [r for r in rows if r.status == "new" and r.kind == "expense"]
    new_income = [r for r in rows if r.status == "new" and r.kind == "income"]
    currencies = sorted({r.currency for r in rows if r.status == "new"})

    def total(items):
        sums: dict[str, Decimal] = defaultdict(Decimal)
        for r in items:
            sums[r.currency] += r.amount
        return {c: str(v) for c, v in sorted(sums.items())}

    dates = [r.date for r in rows if r.status == "new" and r.date]
    return {
        "rows": len(rows),
        "new_expenses": len(new_expense),
        "new_income": len(new_income),
        "duplicates": by_status["duplicate"],
        "skipped": by_status["skipped"],
        "errors": by_status["error"],
        "expense_total": total(new_expense),
        "income_total": total(new_income),
        "currencies": currencies,
        "first_date": min(dates).isoformat() if dates else None,
        "last_date": max(dates).isoformat() if dates else None,
    }
