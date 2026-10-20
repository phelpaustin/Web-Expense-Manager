"""Bank statement import: analyse a file, preview what would happen, then save it.

Stateless on purpose: every call carries the file and the mapping, so nothing is kept on the
server between steps and a preview is computed by the very code that later saves. Nothing is
written until ``/import/commit``.
"""
import io
import json

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from app.api import bill_sync
from app.api.deps import get_current_user
from app.api.expenses import _price_per_unit, fetch_expenses
from app.api.income import fetch_income
from app.api.options import ensure_options, get_or_create_options
from app.core.currency import normalize_currency
from app.core.file_upload import ensure_xlsx_within_limits, read_upload_limited_sync
from app.core.fx import normalize_convertible_currency
from app.core.import_limits import MAX_IMPORT_FILE_BYTES, MAX_IMPORT_ROWS
from app.core.money import MAX_MONEY, quantize_money
from app.core import ai_import
from app.core.rate_limit import import_ai_limit, import_limit, limiter
from app.core.validation import MAX_NAME, MAX_TEXT
from app.db import models
from app.db.database import get_db
from app.logic import statement_import as si
from app.logic.taxonomy import CategoryResolver

router = APIRouter()

PREVIEW_ROWS = 300
GRID_HEAD_ROWS = 15
MAX_OVERRIDES = 10_000


def _load_grid(file: UploadFile) -> list[list[str]]:
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are allowed")
    raw = read_upload_limited_sync(file, MAX_IMPORT_FILE_BYTES)
    try:
        if name.endswith(".xlsx"):
            ensure_xlsx_within_limits(raw)
            df = pd.read_excel(io.BytesIO(raw), header=None, dtype=object, nrows=MAX_IMPORT_ROWS + si.HEADER_SCAN_ROWS + 1)
            grid = si.grid_from_dataframe(df)
        else:
            grid = si.grid_from_csv(raw)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - any reader failure is a bad file, not a server error
        raise HTTPException(status_code=400, detail=f"Could not read the file: {exc}") from exc
    if not any(any(r) for r in grid):
        raise HTTPException(status_code=400, detail="The file is empty")
    return grid


def _parse_json(text: str, what: str, default):
    if not text or not text.strip():
        return default
    try:
        return json.loads(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{what} is not valid JSON") from exc


def _parse_mapping(text: str) -> si.Mapping:
    data = _parse_json(text, "mapping", None)
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="mapping is required")
    try:
        return si.Mapping.model_validate(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid mapping: {exc}") from exc


def _line_map(text: str, what: str, allowed: set[str] | None = None) -> dict[int, str]:
    data = _parse_json(text, what, {})
    if not isinstance(data, dict) or len(data) > MAX_OVERRIDES:
        raise HTTPException(status_code=400, detail=f"{what} must be an object of at most {MAX_OVERRIDES:,} entries")
    out: dict[int, str] = {}
    for key, value in data.items():
        try:
            line = int(key)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{what}: line numbers must be integers") from None
        if not isinstance(value, str) or (allowed is not None and value not in allowed):
            raise HTTPException(status_code=400, detail=f"{what}: unexpected value for line {line}")
        out[line] = value.strip()[:MAX_NAME]
    return out


def _table_and_rows(db: Session, user: models.User, file: UploadFile, mapping_json: str, overrides_json: str, categories_json: str):
    mapping = _parse_mapping(mapping_json)
    grid = _load_grid(file)
    table = si.build_table(grid, mapping.header_row)
    if len(table.rows) > MAX_IMPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"File has more than {MAX_IMPORT_ROWS:,} data rows")
    problems = si.mapping_problems(mapping, table)
    if problems:
        return mapping, table, problems, []
    overrides = _line_map(overrides_json, "overrides", {"expense", "income", "skip"})
    category_overrides = _line_map(categories_json, "categories")
    options = get_or_create_options(db, user.id)
    # Only the person's own records: group expenses are other people's to keep.
    existing = fetch_expenses(db, user.id, scope="personal")
    rows = si.classify(
        table,
        mapping,
        default_currency=options.base_currency or "SEK",
        normalize_currency=normalize_convertible_currency,
        max_amount=MAX_MONEY,
        history=si.HistoryIndex(existing),
        existing_expenses=existing,
        existing_income=fetch_income(db, user.id),
        overrides=overrides,
        category_overrides=category_overrides,
    )
    return mapping, table, [], rows


@router.post("/import/analyze")
@limiter.limit(import_limit)
def analyze(
    request: Request,
    file: UploadFile = File(...),
    header_row: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Read the file and suggest a mapping. ``header_row`` (0-based) forces where the table starts."""
    grid = _load_grid(file)
    forced = None
    if header_row.strip():
        try:
            forced = int(header_row)
        except ValueError:
            raise HTTPException(status_code=400, detail="header_row must be a number") from None
        if not 0 <= forced < min(len(grid), si.HEADER_SCAN_ROWS * 4):
            raise HTTPException(status_code=400, detail="header_row is outside the file")
    result = si.analyse(grid)
    if forced is not None:
        table = si.build_table(grid, forced)
        mapping, notes = si.guess_mapping(table)
        result = si.Analysis(table, mapping, notes)
    table = result.table
    if len(table.rows) > MAX_IMPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"File has more than {MAX_IMPORT_ROWS:,} data rows")
    width = len(table.labels)
    signature = si.header_signature(table.labels)
    mapping, notes, profile = result.mapping, result.notes, None
    saved = (
        db.query(models.ImportProfile)
        .filter(models.ImportProfile.user_id == user.id, models.ImportProfile.signature == signature)
        .order_by(models.ImportProfile.id.desc())
        .first()
    )
    if saved is not None:
        try:
            candidate = si.Mapping.model_validate({**(saved.mapping or {}), "header_row": table.header_row})
            if not si.mapping_problems(candidate, table):
                mapping, profile = candidate, {"id": saved.id, "name": saved.name}
                notes = [f"Used your saved mapping “{saved.name}”."]
        except ValueError:
            pass  # a stale or hand-edited profile is ignored; the guessed mapping is used instead
    return {
        "filename": file.filename,
        "header_row": table.header_row,
        "columns": table.labels,
        "grid_head": [r + [""] * (width - len(r)) for r in grid[:GRID_HEAD_ROWS]],
        "sample": table.rows[:10],
        "total_rows": sum(1 for r in table.rows if any(r)),
        "mapping": mapping.model_dump(),
        "notes": notes,
        "problems": si.mapping_problems(mapping, table),
        "signature": signature,
        "profile": profile,
        "ai_available": ai_import.is_configured(),
    }


@router.post("/import/assist")
@limiter.limit(import_ai_limit)
def assist(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    instruction: str = Form(...),
    user: models.User = Depends(get_current_user),
):
    """Let the AI adjust the mapping from a typed instruction. Only the headers and about ten
    sample rows are sent to the model; nothing is saved, and the result is a mapping to preview."""
    instruction = instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Tell the assistant what you want")
    if len(instruction) > ai_import.MAX_INSTRUCTION_CHARS:
        raise HTTPException(status_code=400, detail=f"Keep the instruction under {ai_import.MAX_INSTRUCTION_CHARS} characters")
    current = _parse_mapping(mapping)
    grid = _load_grid(file)
    table = si.build_table(grid, current.header_row)
    sample = [r for r in table.rows if any(r)][: ai_import.SAMPLE_ROWS]
    try:
        suggestion = ai_import.suggest_mapping(table.labels, sample, current, instruction)
    except ai_import.AssistError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    return {
        "mapping": suggestion.mapping.model_dump(),
        "explanation": suggestion.explanation,
        "notes": suggestion.notes,
        "problems": si.mapping_problems(suggestion.mapping, table),
    }


# ── Saved mappings ("my bank") ────────────────────────────────────────────

MAX_PROFILES = 20


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    signature: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    mapping: si.Mapping


def _profile_out(p: models.ImportProfile) -> dict:
    return {"id": p.id, "name": p.name, "signature": p.signature}


@router.get("/import/profiles")
def list_profiles(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.ImportProfile).filter(models.ImportProfile.user_id == user.id).order_by(models.ImportProfile.name).all()
    return [_profile_out(p) for p in rows]


@router.put("/import/profiles")
def save_profile(payload: ProfileIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Save (or replace) a named mapping for this bank's file layout."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the mapping a name")
    row = db.query(models.ImportProfile).filter(models.ImportProfile.user_id == user.id, models.ImportProfile.name == name).first()
    if row is None:
        count = db.query(models.ImportProfile).filter(models.ImportProfile.user_id == user.id).count()
        if count >= MAX_PROFILES:
            raise HTTPException(status_code=400, detail=f"You can keep at most {MAX_PROFILES} saved mappings")
        row = models.ImportProfile(user_id=user.id, name=name, signature=payload.signature, mapping={})
        db.add(row)
    row.signature = payload.signature
    row.mapping = payload.mapping.model_dump()
    db.commit()
    db.refresh(row)
    return _profile_out(row)


@router.delete("/import/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.get(models.ImportProfile, profile_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved mapping not found")
    db.delete(row)
    db.commit()


@router.post("/import/preview")
@limiter.limit(import_limit)
def preview(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    overrides: str = Form(""),
    categories: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """What importing with this mapping would do. Saves nothing."""
    m, table, problems, rows = _table_and_rows(db, user, file, mapping, overrides, categories)
    if problems:
        return {"problems": problems, "summary": None, "rows": [], "truncated": False}
    # Show what needs attention first (errors, then new rows), but keep file order inside each group.
    shown = rows[:PREVIEW_ROWS]
    return {
        "problems": [],
        "summary": si.summarise(rows),
        "rows": [r.as_dict() for r in shown],
        "truncated": len(rows) > PREVIEW_ROWS,
        "categories": sorted(get_or_create_options(db, user.id).categories or []),
    }


def _clip(text: str, limit: int) -> str:
    return (text or "").strip()[:limit]


@router.post("/import/commit")
@limiter.limit(import_limit)
def commit(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    overrides: str = Form(""),
    categories: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Save the rows the preview called new. Duplicates and skipped rows are left alone."""
    m, table, problems, rows = _table_and_rows(db, user, file, mapping, overrides, categories)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))

    options = get_or_create_options(db, user.id)
    resolver = CategoryResolver(list(options.categories or []))
    learned: set[tuple] = set()
    added_expenses = added_income = 0
    for r in rows:
        if r.status != "new":
            continue
        amount = quantize_money(r.amount)
        if r.kind == "expense":
            category = resolver.resolve(_clip(r.category, MAX_NAME)) or si.UNCATEGORIZED
            subcategory = _clip(r.subcategory, MAX_NAME)
            shop = _clip(r.shop, MAX_NAME)
            expense = models.Expense(
                user_id=user.id, date=r.date, category=category, subcategory=subcategory,
                description=_clip(r.description, MAX_TEXT), amount=amount, quantity=1.0, unit="Count",
                shop=shop, brand="", currency=normalize_currency(r.currency),
            )
            expense.price_per_unit = _price_per_unit(amount, 1.0)
            db.add(expense)
            learned.add((category, subcategory, "Count", shop))
            added_expenses += 1
        else:
            db.add(models.Income(
                user_id=user.id, date=r.date, amount=amount, source=_clip(r.description, MAX_NAME) or "Income",
                note="Imported from bank statement", currency=normalize_currency(r.currency),
            ))
            added_income += 1
    db.commit()
    bill_sync.adopt_after_write(db, user.id)
    for category, subcategory, unit, shop in learned:
        ensure_options(db, user.id, category, subcategory, unit, shop)
    summary = si.summarise(rows)
    return {
        "added_expenses": added_expenses,
        "added_income": added_income,
        "duplicates": summary["duplicates"],
        "skipped": summary["skipped"],
        "errors": summary["errors"],
    }
