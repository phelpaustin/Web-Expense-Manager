"""Item/shop merges and unit normalisation, end to end through the API."""
import pytest

PRICES = "/api/analytics/price-trends"


def buy(client, h, item, price, *, date="2026-01-10", qty=1, unit="Count", shop="ICA", category="Food"):
    r = client.post(
        "/api/expenses",
        json={"date": date, "category": category, "description": item, "amount": str(price),
              "quantity": qty, "unit": unit, "shop": shop, "currency": "SEK"},
        headers=h,
    )
    assert r.status_code in (200, 201), r.text


def trends(client, h):
    return client.get(PRICES, headers=h).json()


def merge(client, h, kind, names, canonical):
    return client.post("/api/aliases/merge", json={"kind": kind, "names": names, "canonical": canonical}, headers=h)


# --- unit normalisation ----------------------------------------------------------------

def test_prices_logged_in_g_and_kg_are_one_item_compared_per_kg(client, make_user):
    _, h = make_user()
    buy(client, h, "Flour", 20, qty=1, unit="kg", date="2026-01-05")      # 20 per kg
    buy(client, h, "Flour", 12, qty=500, unit="g", date="2026-02-05")     # 0.024 per g = 24 per kg

    rows = trends(client, h)

    assert len(rows) == 1
    t = rows[0]
    assert (t["item"], t["unit"], t["purchases"]) == ("Flour", "Kg", 2)
    assert (float(t["first_price"]), float(t["last_price"])) == (20.0, 24.0)


def test_ml_and_litres_combine_but_litres_and_kilos_do_not(client, make_user):
    _, h = make_user()
    buy(client, h, "Oil", 40, qty=1, unit="Litre", date="2026-01-01")
    buy(client, h, "Oil", 22, qty=500, unit="ml", date="2026-02-01")   # 44 per litre
    buy(client, h, "Oil", 90, qty=1, unit="kg", date="2026-03-01")     # a different kind of unit
    buy(client, h, "Oil", 95, qty=1, unit="kg", date="2026-04-01")

    by_unit = {t["unit"]: t for t in trends(client, h)}

    assert set(by_unit) == {"Litre", "Kg"}
    assert by_unit["Litre"]["purchases"] == 2 and float(by_unit["Litre"]["last_price"]) == 44.0
    assert by_unit["Kg"]["purchases"] == 2


def test_shop_comparison_and_history_accept_any_spelling_of_the_unit(client, make_user):
    _, h = make_user()
    buy(client, h, "Flour", 20, qty=1, unit="kg", shop="ICA", date="2026-01-05")
    buy(client, h, "Flour", 12, qty=500, unit="g", shop="Lidl", date="2026-02-05")
    base = "/api/analytics/price-trends"

    for unit in ("Kg", "kg", "g"):
        shops = client.get(f"{base}/shops", params={"item": "Flour", "unit": unit}, headers=h).json()
        assert [(s["shop"], float(s["avg_price"])) for s in shops] == [("ICA", 20.0), ("Lidl", 24.0)]
    history = client.get(f"{base}/history", params={"item": "Flour", "unit": "Kg"}, headers=h).json()
    assert [float(p["price"]) for p in history] == [20.0, 24.0]


# --- automatic name matching -----------------------------------------------------------

def test_case_and_spacing_variants_are_one_item_without_any_merge(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk", 10, date="2026-01-01")
    buy(client, h, "milk", 11, date="2026-02-01")
    buy(client, h, "MILK ", 12, date="2026-03-01")

    rows = trends(client, h)

    assert len(rows) == 1
    assert rows[0]["purchases"] == 3
    assert rows[0]["item"].lower() == "milk"


# --- merges ----------------------------------------------------------------------------

def test_merging_item_names_combines_their_price_history(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk", 10, date="2026-01-01")
    buy(client, h, "Milk", 12, date="2026-02-01")
    buy(client, h, "Milk 1L", 14, date="2026-03-01")
    buy(client, h, "Milk 1L", 16, date="2026-04-01")
    assert sorted(t["item"] for t in trends(client, h)) == ["Milk", "Milk 1L"]

    r = merge(client, h, "item", ["Milk 1L"], "Milk")

    assert r.status_code == 200 and r.json() == {"canonical": "Milk", "merged": 1}
    rows = trends(client, h)
    assert len(rows) == 1
    assert (rows[0]["item"], rows[0]["purchases"]) == ("Milk", 4)
    assert (float(rows[0]["first_price"]), float(rows[0]["last_price"])) == (10.0, 16.0)


def test_merge_never_changes_the_stored_expenses(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk 1L", 14)
    merge(client, h, "item", ["Milk 1L"], "Milk")

    listed = client.get("/api/expenses", headers=h).json()
    items = listed["items"] if isinstance(listed, dict) else listed
    assert [e["description"] for e in items] == ["Milk 1L"]


def test_undoing_a_merge_restores_the_original_grouping(client, make_user):
    _, h = make_user()
    for d, item in (("2026-01-01", "Milk"), ("2026-02-01", "Milk"), ("2026-03-01", "Milk 1L"), ("2026-04-01", "Milk 1L")):
        buy(client, h, item, 10, date=d)
    merge(client, h, "item", ["Milk 1L"], "Milk")
    alias_id = client.get("/api/aliases", headers=h).json()["items"][0]["id"]

    assert client.delete(f"/api/aliases/{alias_id}", headers=h).status_code == 204

    assert sorted(t["item"] for t in trends(client, h)) == ["Milk", "Milk 1L"]
    assert client.get("/api/aliases", headers=h).json() == {"items": [], "shops": []}


def test_merging_shops_combines_the_shop_comparison(client, make_user):
    _, h = make_user()
    buy(client, h, "Rice", 30, shop="ICA", date="2026-01-01")
    buy(client, h, "Rice", 34, shop="ICA Maxi", date="2026-02-01")
    buy(client, h, "Rice", 25, shop="Lidl", date="2026-03-01")
    url = "/api/analytics/price-trends/shops"
    before = {s["shop"] for s in client.get(url, params={"item": "Rice"}, headers=h).json()}
    assert before == {"ICA", "ICA Maxi", "Lidl"}

    merge(client, h, "shop", ["ICA Maxi"], "ICA")

    after = client.get(url, params={"item": "Rice"}, headers=h).json()
    assert {s["shop"] for s in after} == {"ICA", "Lidl"}
    ica = next(s for s in after if s["shop"] == "ICA")
    assert ica["times_bought"] == 2 and float(ica["avg_price"]) == 32.0


def test_asking_for_a_merged_name_by_its_old_spelling_still_finds_the_item(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk", 10, date="2026-01-01")
    buy(client, h, "Milk 1L", 14, date="2026-02-01")
    merge(client, h, "item", ["Milk 1L"], "Milk")

    history = client.get("/api/analytics/price-trends/history", params={"item": "Milk 1L"}, headers=h).json()

    assert [float(p["price"]) for p in history] == [10.0, 14.0]


def test_merges_never_chain(client, make_user):
    _, h = make_user()
    merge(client, h, "item", ["Milk 1L"], "Milk")
    merge(client, h, "item", ["Milk"], "Whole milk")        # the old target is merged away

    rules = {r["alias"]: r["canonical"] for r in client.get("/api/aliases", headers=h).json()["items"]}
    assert rules == {"Milk 1L": "Whole milk", "Milk": "Whole milk"}


def test_merging_into_a_name_that_is_itself_merged_goes_to_its_final_target(client, make_user):
    _, h = make_user()
    merge(client, h, "item", ["Milk"], "Whole milk")

    r = merge(client, h, "item", ["Milk 1L"], "Milk")

    assert r.json()["canonical"] == "Whole milk"


def test_merge_rejects_nonsense(client, make_user):
    _, h = make_user()
    assert merge(client, h, "item", ["Milk"], "milk ").status_code == 400          # same name as the target
    assert merge(client, h, "item", ["   "], "Milk").status_code == 400            # nothing to merge
    assert client.post("/api/aliases/merge", json={"kind": "brand", "names": ["a"], "canonical": "b"}, headers=h).status_code == 422
    assert client.post("/api/aliases/merge", json={"kind": "item", "names": [], "canonical": "b"}, headers=h).status_code == 422
    assert client.post("/api/aliases/merge", json={"kind": "item", "names": ["a"], "canonical": "x" * 201}, headers=h).status_code == 422


def test_merging_again_updates_rather_than_duplicates(client, make_user):
    _, h = make_user()
    merge(client, h, "item", ["Milk 1L"], "Milk")
    merge(client, h, "item", ["milk 1l"], "Whole milk")

    rules = client.get("/api/aliases", headers=h).json()["items"]
    assert len(rules) == 1 and rules[0]["canonical"] == "Whole milk"


# --- isolation and cleanup -------------------------------------------------------------

def test_merges_are_private_to_their_owner_and_need_a_login(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    merge(client, alice, "item", ["Milk 1L"], "Milk")
    alias_id = client.get("/api/aliases", headers=alice).json()["items"][0]["id"]

    assert client.get("/api/aliases", headers=bob).json() == {"items": [], "shops": []}
    assert client.delete(f"/api/aliases/{alias_id}", headers=bob).status_code == 404
    assert len(client.get("/api/aliases", headers=alice).json()["items"]) == 1
    assert client.get("/api/aliases").status_code == 401
    assert client.post("/api/aliases/merge", json={"kind": "item", "names": ["a"], "canonical": "b"}).status_code == 401


def test_one_users_merges_do_not_affect_another_users_analytics(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    for h in (alice, bob):
        buy(client, h, "Milk", 10, date="2026-01-01")
        buy(client, h, "Milk 1L", 12, date="2026-02-01")
    merge(client, alice, "item", ["Milk 1L"], "Milk")

    assert len(trends(client, alice)) == 1
    assert len(trends(client, bob)) == 0  # one purchase each under two names: no trend yet


def test_deleting_an_account_deletes_its_merges(client, make_user):
    from app.db import models
    from app.db.database import SessionLocal

    uid, h = make_user()
    merge(client, h, "item", ["Milk 1L"], "Milk")

    r = client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h)

    assert r.status_code == 204
    db = SessionLocal()
    try:
        assert db.query(models.NameAlias).filter(models.NameAlias.user_id == uid).count() == 0
    finally:
        db.close()


# --- suggestions -----------------------------------------------------------------------

def test_suggestions_offer_likely_duplicates_and_stop_once_merged(client, make_user):
    _, h = make_user()
    for item, n in (("Banana", 3), ("Bananas", 2), ("Bread", 4)):
        for i in range(n):
            buy(client, h, item, 10, date=f"2026-01-{i + 1:02d}")
    url = "/api/aliases/suggestions"

    groups = client.get(url, params={"kind": "item"}, headers=h).json()["groups"]
    assert len(groups) == 1
    assert groups[0]["suggested"] == "Banana"
    assert {m["name"] for m in groups[0]["names"]} == {"Banana", "Bananas"}

    merge(client, h, "item", ["Bananas"], "Banana")
    assert client.get(url, params={"kind": "item"}, headers=h).json()["groups"] == []


def test_shop_suggestions_work_the_same_way(client, make_user):
    _, h = make_user()
    for shop in ("Willys", "Willys", "Willys Malmö"):
        buy(client, h, "Rice", 10, shop=shop)
    # "Willys Malmö" is not a size or a typo of "Willys", so it is not suggested automatically.
    assert client.get("/api/aliases/suggestions", params={"kind": "shop"}, headers=h).json()["groups"] == []

    buy(client, h, "Rice", 10, shop="Wilys")  # a typo

    groups = client.get("/api/aliases/suggestions", params={"kind": "shop"}, headers=h).json()["groups"]
    assert len(groups) == 1 and groups[0]["suggested"] == "Willys"
    assert {m["name"] for m in groups[0]["names"]} == {"Willys", "Wilys"}


def test_suggestions_need_a_valid_kind(client, make_user):
    _, h = make_user()
    assert client.get("/api/aliases/suggestions", params={"kind": "brand"}, headers=h).status_code == 422
