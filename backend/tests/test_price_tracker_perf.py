"""The faster price tracker gives exactly the results of the straightforward pipeline."""
import datetime as dt
import random
import statistics
from decimal import Decimal

import pytest
from fastapi.encoders import jsonable_encoder

from app.api.expenses import fetch_expenses_in_reporting_currency
from app.core.money import quantize_money
from app.db import models
from app.db.database import SessionLocal
from app.logic import names, price_tracker

TODAY = dt.date.today()


# ── the exact statistics ────────────────────────────────────────────────
def test_mean_and_pstdev_match_the_statistics_module_on_decimal_prices():
    rng = random.Random(7)
    for _ in range(500):
        prices = [Decimal(rng.randint(1, 5_000_000)) / Decimal(10_000) for _ in range(rng.randint(1, 40))]
        assert price_tracker.mean(prices) == statistics.mean(prices)
        assert quantize_money(price_tracker.mean(prices)) == quantize_money(statistics.mean(prices))
        if len(prices) > 1:
            assert round(price_tracker.pstdev(prices), 2) == round(statistics.pstdev(prices), 2)


def test_mean_and_pstdev_still_accept_plain_numbers():
    assert price_tracker.mean([1, 2, 3]) == 2
    assert price_tracker.pstdev([1.0, 3.0]) == 1.0
    assert price_tracker.pstdev([5]) == 0


# ── name cleaning is unchanged by the cache ─────────────────────────────
@pytest.mark.parametrize("value", [None, "", "  Milk   1L ", "MILK.", "Mjölk", 12, " a\tb\n c "])
def test_clean_name_and_name_key_values(value):
    cleaned = " ".join(str(value or "").split())
    assert names.clean_name(value) == cleaned
    assert names.name_key(value) == cleaned.casefold().strip(" .,;:")


# ── detail endpoints == the old pipeline ────────────────────────────────
def _seed(client, make_user):
    uid, h = make_user()
    rows = []
    rng = random.Random(3)
    items = ["Milk", "milk ", "Milk 1L", "Arla Milk", "Bread", "BREAD", "Rice", "Eggs"]
    # the spelling that is most common for the shop in the Milk rows differs from the overall one
    shops = ["Coop", "COOP", "Lidl", "ICA", "", "ica"]
    for i in range(120):
        rows.append(dict(
            user_id=uid, date=TODAY - dt.timedelta(days=rng.randint(0, 200)), category=rng.choice(["Dairy", "Bakery"]),
            subcategory="", description=rng.choice(items), amount=Decimal(rng.randint(500, 9000)) / 100,
            quantity=float(rng.choice([1, 1, 2, 0.5])), unit=rng.choice(["Count", "Kg", "g"]),
            shop=rng.choice(shops), brand=rng.choice(["", "Arla", "Garant"]),
            currency=rng.choice(["SEK", "SEK", "USD", "EUR"]), price_per_unit=Decimal(rng.randint(100, 9000)) / 100,
            bill_total_only=False,
        ))
    # a row in a currency that has no exchange rate: skipped everywhere
    rows.append(dict(user_id=uid, date=TODAY, category="Dairy", subcategory="", description="Milk", amount=Decimal("9"),
                     quantity=1.0, unit="Count", shop="Coop", brand="", currency="XYZ", price_per_unit=Decimal("9"),
                     bill_total_only=False))
    db = SessionLocal()
    db.bulk_insert_mappings(models.Expense, rows)
    db.commit()
    db.close()
    # merges: "Milk 1L" and "Arla Milk" are Milk; Lidl is ICA
    assert client.post("/api/aliases/merge", json={"kind": "item", "names": ["Milk 1L", "Arla Milk"], "canonical": "Milk"}, headers=h).status_code == 200
    assert client.post("/api/aliases/merge", json={"kind": "shop", "names": ["Lidl"], "canonical": "ICA"}, headers=h).status_code == 200
    return uid, h


def _old_pipeline_rows(uid):
    """What the endpoints did before: convert everything, then apply the merges."""
    from app.api.aliases import load_alias_maps

    db = SessionLocal()
    try:
        item_aliases, shop_aliases = load_alias_maps(db, uid)
        rows = names.canonicalise(fetch_expenses_in_reporting_currency(db, uid), item_aliases, shop_aliases)
        return rows, item_aliases
    finally:
        db.close()


ITEMS = ["Milk", "milk 1l", "Arla Milk", "bread", "Rice", "Eggs", "Nothing Bought"]


@pytest.mark.parametrize("item", ITEMS)
def test_detail_history_and_shops_equal_the_old_pipeline(client, make_user, item):
    uid, h = _seed(client, make_user)
    rows, aliases = _old_pipeline_rows(uid)
    resolved = names.resolve_name(item, aliases)

    for unit in (None, "Count", "Kg"):
        q = {"item": item, **({"unit": unit} if unit else {})}
        detail = client.get("/api/analytics/price-trends/detail", params=q, headers=h)
        assert detail.status_code == 200, detail.text
        assert detail.json() == jsonable_encoder(price_tracker.price_detail(rows, resolved, unit, None, None, None))

        hist = client.get("/api/analytics/price-trends/history", params=q, headers=h).json()
        assert hist == jsonable_encoder(price_tracker.price_history(rows, resolved, unit, None, None, None))

        shops = client.get("/api/analytics/price-trends/shops", params=q, headers=h).json()
        assert shops == jsonable_encoder(price_tracker.shop_comparison(rows, resolved, unit, None, None, None))


def test_detail_with_brand_and_shop_choices_equals_the_old_pipeline(client, make_user):
    uid, h = _seed(client, make_user)
    rows, aliases = _old_pipeline_rows(uid)
    params = {"item": "Milk", "brand": "Arla", "shop": ["COOP", "ICA"]}
    got = client.get("/api/analytics/price-trends/detail", params=params, headers=h).json()
    assert got == jsonable_encoder(price_tracker.price_detail(rows, "Milk", None, None, "Arla", ["COOP", "ICA"]))


def test_the_trend_list_equals_the_old_pipeline(client, make_user):
    uid, h = _seed(client, make_user)
    rows, _ = _old_pipeline_rows(uid)
    got = client.get("/api/analytics/price-trends", headers=h).json()
    assert got == jsonable_encoder(price_tracker.price_trends(rows))
    assert len(got) > 3


def test_canonicalise_only_item_is_the_same_rows_the_full_result_has_for_that_item():
    rows = [
        {"description": d, "shop": s, "amount": 1}
        for d, s in [("Milk", "Coop"), ("milk", "COOP"), ("Milk 1L", "Coop"), ("Bread", "ICA"), ("bread ", "ica"), ("", "x")]
    ]
    aliases = {names.name_key("Milk 1L"): "Milk"}
    full = names.canonicalise(rows, aliases, {})
    for item in ("Milk", "milk 1l", "BREAD", "unknown", ""):
        wanted = names.name_key(names.resolve_name(item, aliases))
        expected = [r for r in full if names.name_key(r["description"]) == wanted]
        assert names.canonicalise(rows, aliases, {}, only_item=item) == expected


def test_a_shared_shop_name_keeps_the_spelling_it_has_overall(client, make_user):
    """Shown spellings are decided from all expenses, not just the requested item's."""
    uid, h = make_user()
    db = SessionLocal()
    base = dict(user_id=uid, category="Dairy", subcategory="", quantity=1.0, unit="Count", brand="", currency="SEK", bill_total_only=False)
    db.bulk_insert_mappings(models.Expense, (
        # Milk was bought at "Coop" twice (the most common spelling within Milk) ...
        [dict(base, date=TODAY - dt.timedelta(days=i), description="Milk", amount=Decimal("10"), price_per_unit=Decimal("10"), shop="Coop") for i in range(2)]
        + [dict(base, date=TODAY - dt.timedelta(days=5), description="Milk", amount=Decimal("11"), price_per_unit=Decimal("11"), shop="COOP")]
        # ... but overall "COOP" is the most common spelling
        + [dict(base, date=TODAY - dt.timedelta(days=10 + i), description="Bread", amount=Decimal("5"), price_per_unit=Decimal("5"), shop="COOP") for i in range(5)]
    ))
    db.commit()
    db.close()
    shops = client.get("/api/analytics/price-trends/shops", params={"item": "Milk"}, headers=h).json()
    assert [s["shop"] for s in shops] == ["COOP"]
    assert shops[0]["times_bought"] == 3


def test_large_responses_are_gzipped(client, make_user):
    _, h = _seed(client, make_user)
    r = client.get("/api/analytics/price-trends", headers={**h, "Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert len(r.json()) > 3  # the client decodes it transparently
