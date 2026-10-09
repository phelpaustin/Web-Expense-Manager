"""Tolerant parsing of values that arrive in uploaded bank/expense exports.

Real exports vary by country and bank: ``;``-delimited CSVs, decimal commas
(``1 234,56``), thousands separators, trailing minus signs, accounting
parentheses, currency symbols, Windows-1252 text. These helpers accept all of
that and return exact ``Decimal`` values instead of guessing silently.
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation

import pandas as pd

_MINUS_SIGNS = "\u2212\u2012\u2013\u2014"  # unicode minus / dashes used as minus
_STRIP = re.compile(r"[^\d,.\-]")


def parse_amount(value) -> Decimal:
    """Parse a money value into a finite Decimal, or raise ValueError.

    Accepts numbers and strings such as ``1234.5``, ``1,234.50``, ``1.234,50``,
    ``1 234,50``, ``-12,50``, ``12.50-``, ``(12.50)``, ``kr 99``, ``$5``.
    A lone comma or dot is a decimal separator unless it is followed by exactly
    three digits and is the only one of its kind (``1,234`` -> 1234 but
    ``1.234`` stays 1.234, since a dot is far more often a decimal point).
    """
    if value is None:
        raise ValueError("missing amount")
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and not pd.notna(value):
            raise ValueError("missing amount")
        number = Decimal(str(value))
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            raise ValueError("missing amount")
        for ch in _MINUS_SIGNS:
            text = text.replace(ch, "-")
        negative = text.startswith("(") and text.endswith(")") or text.endswith("-") or text.startswith("-")
        cleaned = _STRIP.sub("", text).replace("-", "")
        if not cleaned or not re.search(r"\d", cleaned):
            raise ValueError(f"not a number: {value!r}")
        cleaned = _normalise_separators(cleaned)
        try:
            number = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"not a number: {value!r}") from exc
        if negative:
            number = -number
    if not number.is_finite():
        raise ValueError(f"not a number: {value!r}")
    return number


def _normalise_separators(s: str) -> str:
    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        # The separator that appears last is the decimal point; the other groups thousands.
        decimal_sep = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        return s.replace(thousands, "").replace(decimal_sep, ".")
    if has_comma:
        if s.count(",") > 1:
            return s.replace(",", "")  # 1,234,567
        head, tail = s.split(",")
        return f"{head}{tail}" if len(tail) == 3 and head else f"{head}.{tail}"
    if has_dot and s.count(".") > 1:
        return s.replace(".", "")  # 1.234.567
    return s


def decode_text(raw: bytes) -> str:
    """Decode an uploaded text file: UTF-8 (with or without BOM), else Windows-1252."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def read_csv_bytes(raw: bytes, nrows: int | None = None) -> pd.DataFrame:
    """Read an uploaded CSV with every cell as text, detecting ``,`` ``;`` tab or ``|``.

    Cells stay strings so amounts and dates are parsed by us (see parse_amount)
    rather than guessed by pandas; blank cells become NaN.
    """
    text = decode_text(raw)
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    return pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, nrows=nrows, skipinitialspace=True)
