from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import PlainSerializer

CENT = Decimal("0.01")


def as_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc


def quantize_money(value) -> Decimal:
    return as_decimal(value).quantize(CENT)

# Largest amount a Numeric(12, 2) column can hold. Request models cap money
# fields at this so an oversized value is a 422, not a database overflow (500).
MAX_MONEY = Decimal("9999999999.99")


def _json_number(value: Decimal):
    """A whole number stays an int, anything else becomes a float (what FastAPI's
    jsonable_encoder does for the endpoints that return plain dicts)."""
    return int(value) if value == value.to_integral_value() and value.as_tuple().exponent >= 0 else float(value)


# Response-model money fields. Pydantic would otherwise send Decimals as strings
# ("12.50") while every dict-returning endpoint sends numbers (12.5); the frontend
# should see one format.
JsonDecimal = Annotated[Decimal, PlainSerializer(_json_number, return_type=float | int, when_used="json")]
