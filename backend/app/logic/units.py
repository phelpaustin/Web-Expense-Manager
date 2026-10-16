"""Unit normalisation, so prices logged in different units of one kind can be compared.

price_per_unit means "price per 1 of whatever unit the row was logged in", so 0.02 per
g and 20 per kg are the same price but look nothing alike. Every unit of a known kind
(mass, volume, length, count) is mapped to one base unit and a factor, so a price can
be restated per base unit. Units we don't recognise (Bunch, Pack, ...) are left exactly
as they are and only ever compare with themselves.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import NamedTuple


class NormalisedUnit(NamedTuple):
    label: str  # the base unit's display name ("Kg"), or the unit as typed if unknown
    factor: Decimal  # how many base units one of this unit is (g -> Decimal("0.001"))
    family: str | None  # "mass" | "volume" | "length" | "count", None when unknown


def _family(label: str, family: str, spellings: dict[str, str]) -> dict[str, tuple[str, Decimal, str]]:
    return {name: (label, Decimal(factor), family) for name, factor in spellings.items()}


_KNOWN: dict[str, tuple[str, Decimal, str]] = {}
_KNOWN.update(_family("Kg", "mass", {
    "kg": "1", "kgs": "1", "kilo": "1", "kilos": "1", "kilogram": "1", "kilograms": "1",
    "hg": "0.1", "hektogram": "0.1",
    "g": "0.001", "gr": "0.001", "gram": "0.001", "grams": "0.001", "gramme": "0.001", "grammes": "0.001",
    "gm": "0.001", "gms": "0.001", "grm": "0.001", "grms": "0.001",
    "mg": "0.000001",
    "lb": "0.45359237", "lbs": "0.45359237", "pound": "0.45359237", "pounds": "0.45359237",
    "oz": "0.028349523125", "ounce": "0.028349523125", "ounces": "0.028349523125",
}))
_KNOWN.update(_family("Litre", "volume", {
    "l": "1", "lt": "1", "ltr": "1", "ltrs": "1", "liter": "1", "liters": "1", "litre": "1", "litres": "1",
    "dl": "0.1", "deciliter": "0.1", "decilitre": "0.1",
    "cl": "0.01", "centiliter": "0.01", "centilitre": "0.01",
    "ml": "0.001", "mls": "0.001", "milliliter": "0.001", "milliliters": "0.001", "millilitre": "0.001", "millilitres": "0.001",
}))
_KNOWN.update(_family("Meter", "length", {
    "m": "1", "meter": "1", "meters": "1", "metre": "1", "metres": "1",
    "km": "1000", "kilometer": "1000", "kilometre": "1000",
    "cm": "0.01", "centimeter": "0.01", "centimetre": "0.01", "centimeters": "0.01", "centimetres": "0.01",
    "mm": "0.001", "millimeter": "0.001", "millimetre": "0.001",
}))
_KNOWN.update(_family("Count", "count", {
    "count": "1", "pcs": "1", "pc": "1", "piece": "1", "pieces": "1", "st": "1", "styck": "1",
    "unit": "1", "units": "1", "item": "1", "items": "1", "each": "1", "ea": "1",
    "dozen": "12", "doz": "12",
}))

_SPACES = re.compile(r"\s+")


def normalise_unit(raw) -> NormalisedUnit:
    """The base unit and conversion factor for a unit as the user typed it.

    Matching ignores case, spaces and a trailing full stop ("KG", "kg.", "Kilo gram").
    An empty unit means Count, as everywhere else in the app. An unrecognised unit is
    returned as typed (trimmed) with factor 1 and no family.
    """
    text = _SPACES.sub(" ", str(raw or "").strip())
    if not text:
        return NormalisedUnit("Count", Decimal(1), "count")
    key = text.casefold().rstrip(".").replace(" ", "")
    hit = _KNOWN.get(key)
    if hit is None:
        return NormalisedUnit(text, Decimal(1), None)
    return NormalisedUnit(*hit)


def unit_label(raw) -> str:
    """Just the normalised unit's name: the key two rows must share to be compared."""
    return normalise_unit(raw).label


def to_base_price(price, raw_unit) -> Decimal:
    """A price per one `raw_unit` restated per one base unit (0.02 per g -> 20 per Kg)."""
    return Decimal(str(price)) / normalise_unit(raw_unit).factor
