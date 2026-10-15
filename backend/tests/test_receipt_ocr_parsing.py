"""Receipt text parsing: which number is the amount paid, and which date is the receipt's."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.logic import receipt_ocr as ocr


@pytest.mark.parametrize(
    "text, expected",
    [
        # The subtotal must not be mistaken for the total (it used to win).
        ("Milk 20.00\nSubtotal 90.00\nVAT 10.00\nTotal 100.00", D("100.00")),
        ("Sub-Total: 90.00\nTOTAL: 100.00", D("100.00")),
        ("Delsumma 90,00\nAtt betala 100,00", D("100.00")),
        # Thousands separators used to cut the number off ("1,234.50" -> 1.23).
        ("Total: 1,234.50", D("1234.50")),
        ("Total 1 234,50 kr", D("1234.50")),
        ("Total 1\u00a0234,50 kr", D("1234.50")),
        ("Totalt 1.234,50", D("1234.50")),
        ("Total CHF 1'234.50", D("1234.50")),
        ("Total: $ 12.99", D("12.99")),
        ("Att betala 249,00", D("249.00")),
        # The amount to pay is printed last; later lines win.
        ("Total 50.00\nTotal 80.00", D("80.00")),
        # Lines about VAT / change / tips are not the amount paid.
        ("Total 100.00\nTotal VAT 20.00", D("100.00")),
        ("Total 100.00\nChange total 0.00", D("100.00")),
        # Nothing clearly stated -> None, never a guess.
        ("Thank you for shopping", None),
        ("Total items: 3", None),
        ("Total 0.00", None),
        # Larger than the database can hold is a misread, not a bill.
        ("Total 99999999999999.00", None),
    ],
)
def test_parse_amount(text, expected):
    assert ocr._parse_amount(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Date 2026-07-03", dt.date(2026, 7, 3)),
        ("03.07.2026", dt.date(2026, 7, 3)),
        ("3/7/2026", dt.date(2026, 7, 3)),
        # Both orders valid: read day-first.
        ("03/07/2026", dt.date(2026, 7, 3)),
        # Only one order is valid, so it is used (it used to return nothing).
        ("07/13/2026", dt.date(2026, 7, 13)),
        ("13/07/2026", dt.date(2026, 7, 13)),
        # An impossible date is skipped and the next one used.
        ("31/02/2026 then 2026-03-01", dt.date(2026, 3, 1)),
        ("no date here", None),
    ],
)
def test_parse_date(text, expected):
    assert ocr._parse_date(text) == expected


def test_extract_fields_reads_all_three(monkeypatch):
    text = "LIDL\n2026-07-21\nMilk 20.00\nSubtotal 90.00\nTotal 1,100.00"
    monkeypatch.setattr(ocr, "_text_from_pdf", lambda data: text)
    monkeypatch.setattr(ocr, "HAS_PDF", True)
    got = ocr.extract_fields(b"%PDF", "application/pdf")
    assert got["shop"] == "LIDL"
    assert got["date"] == dt.date(2026, 7, 21)
    assert got["amount"] == D("1100.00")
