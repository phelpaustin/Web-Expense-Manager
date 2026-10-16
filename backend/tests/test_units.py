from decimal import Decimal as D

import pytest

from app.logic.units import normalise_unit, to_base_price, unit_label


@pytest.mark.parametrize(
    "raw, label, factor",
    [
        ("Kg", "Kg", "1"), ("kg", "Kg", "1"), ("KG", "Kg", "1"), ("kg.", "Kg", "1"), ("Kilo", "Kg", "1"),
        ("g", "Kg", "0.001"), ("Gram", "Kg", "0.001"), ("hg", "Kg", "0.1"), ("lb", "Kg", "0.45359237"),
        ("Litre", "Litre", "1"), ("L", "Litre", "1"), ("liter", "Litre", "1"), ("ltr", "Litre", "1"),
        ("ml", "Litre", "0.001"), ("cl", "Litre", "0.01"), ("dl", "Litre", "0.1"),
        ("Meter", "Meter", "1"), ("m", "Meter", "1"), ("cm", "Meter", "0.01"), ("km", "Meter", "1000"),
        ("Count", "Count", "1"), ("pcs", "Count", "1"), ("st", "Count", "1"), ("dozen", "Count", "12"),
        # Case, inner spacing and surrounding whitespace never matter.
        ("  Kilo  gram ", "Kg", "1"), ("Milli Litre", "Litre", "0.001"),
        # Nothing logged means Count, as everywhere else in the app.
        ("", "Count", "1"), (None, "Count", "1"), ("   ", "Count", "1"),
    ],
)
def test_known_units(raw, label, factor):
    n = normalise_unit(raw)
    assert (n.label, n.factor) == (label, D(factor))


def test_unknown_units_are_kept_as_typed_and_only_compare_with_themselves():
    n = normalise_unit("  Bunch ")
    assert n.label == "Bunch" and n.factor == 1 and n.family is None
    assert unit_label("Bunch") != unit_label("Pack")


def test_families():
    assert normalise_unit("g").family == "mass"
    assert normalise_unit("ml").family == "volume"
    assert normalise_unit("cm").family == "length"
    assert normalise_unit("pcs").family == "count"


def test_a_price_per_gram_is_the_same_price_as_per_kg():
    assert to_base_price("0.02", "g") == D("20")
    assert to_base_price("20", "kg") == D("20")
    assert to_base_price("0.012", "ml") == D("12")  # per litre
    assert to_base_price("5", "dozen") == D("5") / 12
