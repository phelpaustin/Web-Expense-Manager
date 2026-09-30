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

_AMOUNT_RE = re.compile(
    r"(?:total|sum|amount due|att betala|grand total)\s*[:\-]?\s*\$?\s*([\d]+[.,]\d{2})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{2}[/.]\d{2}[/.]\d{4})")


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
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_date(text: str) -> datetime.date | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
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
