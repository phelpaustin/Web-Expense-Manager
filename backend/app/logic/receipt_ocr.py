"""Best-effort receipt text extraction, used to autofill a pending bill's
shop/date/amount from an uploaded PDF/photo instead of leaving it blank.

Two independent, optional extraction paths so this degrades gracefully:
  - PDFs: pypdf (pure Python) pulls embedded text — works on any deployment.
  - Images: pytesseract + Pillow, which additionally needs the `tesseract-ocr`
    system binary. It is NOT preinstalled on Render's native Python runtime,
    so image OCR only works where that binary is available (e.g. local dev
    with `apt/brew install tesseract-ocr`, or a Docker-based deployment).
Never raises — a failed/unavailable extraction just returns empty fields.
"""
from __future__ import annotations

import datetime
import io
import re
from decimal import Decimal

from app.core.money import MAX_MONEY, quantize_money
from app.core.parsing import parse_amount

try:
    from pypdf import PdfReader

    HAS_PDF = True
except Exception:
    HAS_PDF = False

try:
    import pytesseract
    from PIL import Image

    HAS_IMAGE_OCR = True
except Exception:
    HAS_IMAGE_OCR = False

# A line that states the amount to pay. "total" must stand alone: it must not be
# the tail of another word, so "Subtotal" / "Delsumma" never match. Several
# languages' wording is accepted; a currency symbol or 3-letter code may sit before the number.
_TOTAL_KEYWORD = (
    r"(?<![A-Za-z])"
    r"(?:grand\s+total|total\s+due|amount\s+due|balance\s+due|total|att\s+betala|summa|sum|totalt|belopp)"
    r"(?![A-Za-z])"
)
# One money token with exactly two decimals. Thousands may be grouped with a
# space, non-breaking space, dot, comma or apostrophe: 1234.50, 1,234.50,
# 1.234,50, 1 234,50, 1'234.50. The grouping/decimal ambiguity is settled by
# parse_amount (the separator that appears last is the decimal point).
_MONEY_TOKEN = r"(?:\d{1,3}(?:[ \u00a0.,']\d{3})+|\d+)[.,]\d{2}(?!\d)"
_AMOUNT_RE = re.compile(
    _TOTAL_KEYWORD + r"[\s:\-]*(?:[$\u20ac\u00a3]|kr\.?|[a-z]{3}(?![a-z]))?\s*(" + _MONEY_TOKEN + r")",
    re.IGNORECASE,
)
# Lines that mention a "total" of something other than what was paid.
_NOT_THE_TOTAL = re.compile(
    r"sub[\s\-]*total|delsumma|zwischensumme"
    r"|\b(?:vat|moms|tax|mwst|rabatt|discount|savings?|change|v\u00e4xel|tendered|received|tip|dricks)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{4})(?!\d)")


def _text_from_pdf(data: bytes) -> str:
    if not HAS_PDF:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _text_from_image(data: bytes) -> str:
    if not HAS_IMAGE_OCR:
        return ""
    try:
        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image)
    except Exception:
        return ""


def _parse_amount(text: str) -> Decimal | None:
    """The amount paid, or None when the text doesn't clearly state one.

    The last matching line wins: the amount to pay is printed at the bottom, after
    any subtotal. Lines about VAT, discounts or change are ignored. The number is
    read by parse_amount, so "1,234.50" is 1234.50 and "1 234,50" is 1234.50.
    """
    found: Decimal | None = None
    for line in text.splitlines():
        if _NOT_THE_TOTAL.search(line):
            continue
        match = _AMOUNT_RE.search(line)
        if not match:
            continue
        try:
            value = quantize_money(parse_amount(match.group(1)))
        except (ValueError, ArithmeticError):
            continue
        # A misread (or absurd) figure must not reach a Numeric(12, 2) column.
        if 0 < value <= MAX_MONEY:
            found = value
    return found


def _parse_date(text: str) -> datetime.date | None:
    """The first date on the receipt.

    ISO (2026-07-03) is unambiguous. For 03/07/2026 or 03.07.2026 the day comes
    first unless the second number can only be a day (07/13/2026), in which case the
    US order is used. A date like 03/07/2026 where both orders are valid is read
    day-first.
    """
    for match in _DATE_RE.finditer(text):
        raw = match.group(1)
        if "-" in raw:
            candidates = [("%Y-%m-%d", raw)]
        else:
            first, second, year = (int(x) for x in re.split(r"[/.]", raw))
            fmt = "%m/%d/%Y" if second > 12 and first <= 12 else "%d/%m/%Y"
            candidates = [(fmt, f"{first}/{second}/{year}")]
        for fmt, value in candidates:
            try:
                return datetime.datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _guess_shop(text: str) -> str | None:
    """The first substantial line of a receipt is almost always the shop name."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3:
            return line[:80]
    return None


def extract_fields(data: bytes, content_type: str) -> dict:
    """Best-effort {available, shop, date, amount} from a receipt PDF/photo."""
    if content_type == "application/pdf":
        text, available = _text_from_pdf(data), HAS_PDF
    elif content_type.startswith("image/"):
        text, available = _text_from_image(data), HAS_IMAGE_OCR
    else:
        text, available = "", False

    return {
        "available": available,
        "shop": _guess_shop(text),
        "date": _parse_date(text),
        "amount": _parse_amount(text),
    }
