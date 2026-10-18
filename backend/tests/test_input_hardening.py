"""Blank names, oversized text, and one JSON format for money."""
import datetime as dt

import pytest

TODAY = dt.date.today().isoformat()
LONG = "x" * 201


def _expense(**over):
    return {"date": TODAY, "category": "Food", "description": "Milk", "amount": "12.50", **over}


@pytest.mark.parametrize("field", ["category"])
@pytest.mark.parametrize("blank", ["", "   ", "\t \n"])
def test_blank_required_names_are_rejected(client, make_user, field, blank):
    _, h = make_user()
    assert client.post("/api/expenses", json=_expense(**{field: blank}), headers=h).status_code == 422


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/income", {"date": TODAY, "amount": "5", "source": "   "}),
                ("/api/recurring", {"item": "  ", "amount": "5"}),
        ("/api/groups", {"name": "   "}),
        ("/api/trips", {"name": "   "}),
    ],
)
def test_blank_names_are_rejected_everywhere(client, make_user, path, body):
    _, h = make_user()
    assert client.post(path, json=body, headers=h).status_code == 422


def test_blank_budget_category_is_rejected(client, make_user):
    _, h = make_user()
    assert client.put("/api/budgets", json={"category": "   ", "amount": "5"}, headers=h).status_code == 422


def test_blank_update_is_rejected_and_surrounding_spaces_are_trimmed(client, make_user):
    _, h = make_user()
    created = client.post("/api/expenses", json=_expense(category="  Food  ", shop="  Coop "), headers=h)
    assert created.status_code == 201
    assert created.json()["category"] == "Food" and created.json()["shop"] == "Coop"
    eid = created.json()["id"]
    assert client.put(f"/api/expenses/{eid}", json={"category": "   "}, headers=h).status_code == 422
    assert client.put(f"/api/expenses/{eid}", json={"shop": "   "}, headers=h).json()["shop"] == ""  # optional fields may be emptied


def test_optional_fields_may_still_be_empty(client, make_user):
    _, h = make_user()
    r = client.post("/api/expenses", json=_expense(shop="", brand="", subcategory="", description=""), headers=h)
    assert r.status_code == 201


@pytest.mark.parametrize("field", ["category", "shop", "brand", "subcategory", "unit"])
def test_overlong_names_are_rejected(client, make_user, field):
    _, h = make_user()
    assert client.post("/api/expenses", json=_expense(**{field: LONG}), headers=h).status_code == 422
    assert client.post("/api/expenses", json=_expense(**{field: "x" * 200}), headers=h).status_code == 201


def test_overlong_text_is_rejected(client, make_user):
    _, h = make_user()
    assert client.post("/api/expenses", json=_expense(description="x" * 1001), headers=h).status_code == 422
    assert client.post("/api/income", json={"date": TODAY, "amount": "5", "source": "Job", "note": "n" * 1001}, headers=h).status_code == 422
    assert client.post("/api/bills-ledger/manual", json={"date": TODAY, "shop": "Coop", "amount": "5", "note": "n" * 1001}, headers=h).status_code == 422


def test_bulk_create_is_capped(client, make_user):
    _, h = make_user()
    r = client.post("/api/expenses/bulk", json={"items": [_expense()] * 1001}, headers=h)
    assert r.status_code == 422


def test_overlong_upload_shop_is_rejected(client, make_user):
    _, h = make_user()
    r = client.post("/api/pending-bills/upload", files={"file": ("r.pdf", b"%PDF-1.4\n", "application/pdf")}, data={"shop": LONG}, headers=h)
    assert r.status_code == 422


# ── money is always a JSON number ───────────────────────────────────────
def _money_types(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("amount", "price_per_unit"):
                out.add(type(v).__name__)
            _money_types(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _money_types(v, out)
    return out


def test_money_fields_are_numbers_in_every_response(client, make_user):
    _, h = make_user()
    responses = [
        client.post("/api/expenses", json=_expense(), headers=h),
        client.post("/api/expenses/bulk", json={"items": [_expense(amount="3")]}, headers=h),
        client.post("/api/income", json={"date": TODAY, "amount": "100", "source": "Job"}, headers=h),
        client.post("/api/bills-ledger/manual", json={"date": TODAY, "shop": "Coop", "amount": "20"}, headers=h),
        client.get("/api/expenses", headers=h),
        client.get("/api/income", headers=h),
        client.get("/api/bills", headers=h),
        client.get("/api/bills-ledger/manual", headers=h),
    ]
    seen = set()
    for r in responses:
        assert r.status_code in (200, 201), r.text
        seen |= _money_types(r.json(), set())
    assert seen and seen <= {"int", "float"}, seen


def test_whole_and_fractional_amounts_round_trip(client, make_user):
    _, h = make_user()
    ids = [client.post("/api/income", json={"date": TODAY, "amount": a, "source": "Job"}, headers=h).json() for a in ("100", "12.5", "0.07")]
    assert [i["amount"] for i in ids] == [100, 12.5, 0.07]
    assert all(isinstance(i["amount"], (int, float)) for i in ids)


@pytest.mark.parametrize("path,body", [
    ("/api/options/category", {"name": "   "}),
    ("/api/options/subcategory", {"category": "Food", "name": "   "}),
    ("/api/options/shop", {"name": "   "}),
    ("/api/options/unit", {"name": "   "}),
])
def test_blank_option_names_are_rejected(client, make_user, path, body):
    _, h = make_user()
    assert client.post(path, json=body, headers=h).status_code == 422
