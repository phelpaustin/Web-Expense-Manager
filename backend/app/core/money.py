from decimal import Decimal, InvalidOperation

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
