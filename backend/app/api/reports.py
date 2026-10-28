"""Yearly and monthly spending report: the numbers as JSON, and the same report as an Excel or PDF file."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.aliases import load_alias_maps
from app.api.deps import get_current_user
from app.api.expenses import fetch_expenses_in_reporting_currency_ex
from app.api.income import fetch_income_in_reporting_currency
from app.api.options import get_reporting_currency
from app.core import report_files
from app.db import models
from app.db.database import get_db
from app.logic import names
from app.logic import report as report_logic
from app.logic import shop_scorecard as shop_scorecard_logic

router = APIRouter()

YEAR = Query(default=None, ge=2000, le=2100, description="Calendar year; this year when left out")
MONTH = Query(default=None, ge=1, le=12, description="Leave out for a report on the whole year")


def _build(db: Session, user: models.User, year: int | None, month: int | None, scope: str | None, space_ids: str | None):
    today = date.today()
    year = year or today.year
    expenses, unconverted = fetch_expenses_in_reporting_currency_ex(db, user.id, scope, space_ids)
    item_aliases, shop_aliases = load_alias_maps(db, user.id)
    # Bill totals name their shop in the description; make that the shop first so shop merges cover them.
    rows = names.canonicalise(shop_scorecard_logic.with_bill_shops(expenses), item_aliases, shop_aliases)
    income = fetch_income_in_reporting_currency(db, user.id)
    result = report_logic.build_report(rows, income, year, month, today=today)
    result["years"] = report_logic.years_with_data(rows, today)
    result["currency"] = get_reporting_currency(db, user.id)
    result["unconverted_count"] = unconverted
    return result


@router.get("/reports")
def get_report(
    year: int | None = YEAR,
    month: int | None = MONTH,
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Totals, change from the previous period, spending by category, by month (a year) or by day
    (a month), top shops and largest expenses. Amounts are in the reporting currency; income is the
    user's own whatever the scope."""
    return _build(db, user, year, month, scope, space_ids)


@router.get("/reports/export")
def export_report(
    format: Literal["xlsx", "pdf"] = "xlsx",
    year: int | None = YEAR,
    month: int | None = MONTH,
    scope: str | None = None,
    space_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The report as an Excel workbook (with charts) or a PDF."""
    result = _build(db, user, year, month, scope, space_ids)
    if format == "pdf":
        content, media_type = report_files.report_pdf(result, result["currency"]), report_files.PDF_MEDIA_TYPE
    else:
        content, media_type = report_files.report_xlsx(result, result["currency"]), report_files.XLSX_MEDIA_TYPE
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={report_files.file_stem(result)}.{format}", "Cache-Control": "no-store"},
    )
