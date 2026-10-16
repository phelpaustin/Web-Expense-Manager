"""Categories are case-insensitive: "Milk", "milk" and "MILK" are one category."""
import datetime

import sqlalchemy as sa

from app.db import models
from app.db.category_cleanup import normalise_categories
from app.db.database import SessionLocal

TODAY = datetime.date.today().isoformat()


def add_category(client, h, name):
    return client.post("/api/options/category", json={"name": name}, headers=h)


def categories(client, h):
    return client.get("/api/options", headers=h).json()["categories"]


def spend(client, h, category, amount="10", **extra):
    r = client.post(
        "/api/expenses",
        json={"date": TODAY, "category": category, "description": extra.pop("description", "x"), "amount": amount, "currency": "SEK", **extra},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()


def stored(client, h, **params):
    return client.get("/api/expenses", params={"page_size": 200, **params}, headers=h).json()["items"]


# --- creating a category ---------------------------------------------------------------

def test_creating_a_case_variant_says_the_existing_one_is_already_present(client, make_user):
    _, h = make_user()
    assert add_category(client, h, "Milk").status_code == 200

    for variant in ("milk", "MILK", "  mILk "):
        r = add_category(client, h, variant)
        assert r.status_code == 409
        assert r.json()["detail"] == "“Milk” is already present."
    assert categories(client, h).count("Milk") == 1
    assert [c for c in categories(client, h) if c.lower() == "milk"] == ["Milk"]


def test_creating_the_same_category_twice_is_also_refused(client, make_user):
    _, h = make_user()
    add_category(client, h, "Milk")

    r = add_category(client, h, "Milk")

    assert r.status_code == 409 and "already present" in r.json()["detail"]


def test_a_default_category_counts_too(client, make_user):
    _, h = make_user()
    default = next(c for c in categories(client, h) if c.isalpha())

    r = add_category(client, h, default.upper() if default != default.upper() else default.lower())

    assert r.status_code == 409 and r.json()["detail"] == f"“{default}” is already present."


def test_new_categories_are_tidied_and_blank_ones_refused(client, make_user):
    _, h = make_user()
    assert add_category(client, h, "  Fast    food ").status_code == 200
    assert "Fast food" in categories(client, h)
    assert add_category(client, h, "   ").status_code == 400


def test_a_subcategory_added_under_a_case_variant_goes_under_the_listed_category(client, make_user):
    _, h = make_user()
    add_category(client, h, "Milk")

    r = client.post("/api/options/subcategory", json={"category": "milk", "name": "Oat"}, headers=h)

    body = r.json()
    assert body["subcategories"]["Milk"] == ["Oat"]
    assert "milk" not in body["categories"] and "milk" not in body["subcategories"]


# --- saving records --------------------------------------------------------------------

def test_an_expense_saved_with_a_variant_is_filed_under_the_listed_spelling(client, make_user):
    _, h = make_user()
    add_category(client, h, "Milk")

    assert spend(client, h, "milk")["category"] == "Milk"
    assert spend(client, h, "MILK")["category"] == "Milk"
    assert categories(client, h).count("Milk") == 1
    assert {e["category"] for e in stored(client, h)} == {"Milk"}


def test_editing_an_expense_to_a_variant_corrects_it(client, make_user):
    _, h = make_user()
    add_category(client, h, "Milk")
    e = spend(client, h, "Food")

    r = client.put(f"/api/expenses/{e['id']}", json={"category": "mIlK"}, headers=h)

    assert r.status_code == 200 and r.json()["category"] == "Milk"


def test_a_new_category_is_learned_once_whatever_its_case(client, make_user):
    _, h = make_user()
    spend(client, h, "Snacks")

    assert spend(client, h, "snacks")["category"] == "Snacks"
    assert [c for c in categories(client, h) if c.lower() == "snacks"] == ["Snacks"]


def test_variants_new_to_the_list_in_one_bulk_save_agree(client, make_user):
    _, h = make_user()
    items = [
        {"date": TODAY, "category": c, "description": "x", "amount": "5", "currency": "SEK"}
        for c in ("snacks", "Snacks", "SNACKS", "Snacks")
    ]

    r = client.post("/api/expenses/bulk", json={"items": items}, headers=h)

    assert r.status_code in (200, 201), r.text
    assert {e["category"] for e in r.json()} == {"Snacks"}  # most used spelling wins
    assert [c for c in categories(client, h) if c.lower() == "snacks"] == ["Snacks"]


def test_import_files_filed_under_the_listed_spelling(client, make_user):
    _, h = make_user()
    add_category(client, h, "Milk")
    csv = f"Date,Category,Amount,Description\n{TODAY},milk,10,a\n{TODAY},MILK,11,b\n{TODAY},fruit,5,c\n{TODAY},FRUIT,6,d\n".encode()

    r = client.post("/api/expenses/import", files={"file": ("x.csv", csv, "text/csv")}, headers=h)

    assert r.json()["added"] == 4
    by_desc = {e["description"]: e["category"] for e in stored(client, h)}
    assert by_desc == {"a": "Milk", "b": "Milk", "c": "fruit", "d": "fruit"}  # new ones follow the first seen
    assert [c for c in categories(client, h) if c.lower() == "fruit"] == ["fruit"]


def test_a_recorded_bill_total_uses_the_listed_spelling(client, make_user):
    _, h = make_user()
    client.post("/api/options/count-bills-as-spending", json={"enabled": False}, headers=h)
    add_category(client, h, "Groceries")
    bill = client.post("/api/pending-bills", json={"date": TODAY, "shop": "ICA", "amount": "99"}, headers=h).json()

    client.post(f"/api/bills/{bill['id']}/record-total", json={"category": "groceries"}, headers=h)

    assert [e["category"] for e in stored(client, h)] == ["Groceries"]


def test_recurring_templates_and_the_expenses_they_post_use_the_listed_spelling(client, make_user):
    _, h = make_user()
    add_category(client, h, "Rent")
    t = client.post("/api/recurring", json={"item": "Flat", "amount": "900", "frequency": "Monthly", "category": "rent"}, headers=h).json()
    assert t["category"] == "Rent"

    client.post(f"/api/recurring/{t['id']}/apply", headers=h)

    assert [e["category"] for e in stored(client, h)] == ["Rent"]


def test_a_budget_set_with_a_variant_updates_the_existing_budget(client, make_user):
    _, h = make_user()
    add_category(client, h, "Milk")
    assert client.put("/api/budgets", json={"category": "Milk", "amount": "100"}, headers=h).status_code == 200

    r = client.put("/api/budgets", json={"category": "milk", "amount": "250"}, headers=h)

    assert r.status_code == 200
    db = SessionLocal()
    try:
        rows = db.query(models.Budget).all()
        assert [(b.category, float(b.amount)) for b in rows if b.category.lower() == "milk"] == [("Milk", 250.0)]
    finally:
        db.close()
    assert client.delete("/api/budgets/MILK", headers=h).status_code == 200


def test_the_total_budget_is_not_treated_as_a_category(client, make_user):
    _, h = make_user()
    r = client.put("/api/budgets", json={"category": "__total_monthly__", "amount": "5000"}, headers=h)
    assert r.status_code == 200


def test_another_users_categories_never_matter(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    add_category(client, alice, "Milk")

    assert spend(client, bob, "milk")["category"] == "milk"  # Alice's "Milk" is not Bob's business
    assert [c for c in categories(client, alice) if c.lower() == "milk"] == ["Milk"]
    assert [c for c in categories(client, bob) if c.lower() == "milk"] == ["milk"]


# --- finding things --------------------------------------------------------------------

def test_the_category_and_shop_filters_ignore_case(client, make_user):
    uid, h = make_user()
    spend(client, h, "Food", description="a", shop="ICA")
    spend(client, h, "Food", description="b", shop="ica")
    spend(client, h, "Other", description="c", shop="Lidl")

    assert {e["description"] for e in stored(client, h, category="FOOD")} == {"a", "b"}
    assert {e["description"] for e in stored(client, h, shop="Ica")} == {"a", "b"}
    assert {e["description"] for e in stored(client, h, category="food", shop="ICA")} == {"a", "b"}


def test_search_ignores_case_in_every_field(client, make_user):
    _, h = make_user()
    spend(client, h, "Food", description="Oat Milk", shop="ICA", brand="Oatly")
    spend(client, h, "Other", description="Bread")

    for term in ("oat milk", "OAT MILK", "ica", "OATLY", "food"):
        assert [e["description"] for e in stored(client, h, search=term)] == ["Oat Milk"], term


def test_search_treats_percent_and_underscore_literally(client, make_user):
    _, h = make_user()
    spend(client, h, "Food", description="100% juice")
    spend(client, h, "Food", description="snake_case")
    spend(client, h, "Food", description="Apple")

    assert [e["description"] for e in stored(client, h, search="%")] == ["100% juice"]
    assert [e["description"] for e in stored(client, h, search="_")] == ["snake_case"]
    assert [e["description"] for e in stored(client, h, search="100%")] == ["100% juice"]
    assert len(stored(client, h, search="  ")) == 3  # blank search is no search


# --- repairing existing data -----------------------------------------------------------

def _legacy(db, user_id, category, n=1, group_id=None):
    """An expense written straight to the table, as old data was (no category rules)."""
    for _ in range(n):
        db.execute(sa.insert(models.Expense.__table__).values(
            user_id=user_id, date=datetime.date.today(), category=category, subcategory="", description="x",
            amount=1, quantity=1, unit="Count", shop="", brand="", currency="SEK", price_per_unit=1,
            bill_total_only=False, group_id=group_id,
        ))


def _used(db, user_id):
    rows = db.execute(sa.select(models.Expense.category, sa.func.count()).where(models.Expense.user_id == user_id).group_by(models.Expense.category))
    return dict(rows.all())


def test_repair_unifies_existing_expenses_budgets_recurring_and_the_list(client, make_user):
    uid, h = make_user()
    other, _ = make_user()
    db = SessionLocal()
    try:
        _legacy(db, uid, "Milk", 2)
        _legacy(db, uid, "milk", 1)
        _legacy(db, uid, "MILK", 1)
        _legacy(db, uid, "Bread", 1)
        _legacy(db, other, "milk", 3)  # someone else's, with only one spelling: untouched
        db.execute(sa.insert(models.Budget.__table__), [
            {"user_id": uid, "category": "Milk", "amount": 100, "currency": "SEK"},
            {"user_id": uid, "category": "milk", "amount": 50, "currency": "SEK"},
            {"user_id": uid, "category": "__total_monthly__", "amount": 9000, "currency": "SEK"},
        ])
        db.execute(sa.insert(models.RecurringTemplate.__table__).values(
            user_id=uid, item="Oat drink", category="MILK", amount=30, frequency="Weekly", note="", auto_post=False, currency="SEK",
        ))
        opts = db.query(models.UserOptions).filter(models.UserOptions.user_id == uid).one() if db.query(models.UserOptions).filter(models.UserOptions.user_id == uid).first() else None
        if opts is None:
            db.execute(sa.insert(models.UserOptions.__table__).values(user_id=uid, categories=[], subcategories={}, units=[], shops=[], base_currency="SEK"))
        db.execute(sa.update(models.UserOptions.__table__).where(models.UserOptions.user_id == uid).values(
            categories=["Milk", "milk", "Bread"], subcategories={"milk": ["Dairy"], "Milk": ["Cream"], "Bread": ["Rye"]},
        ))
        db.commit()

        stats = normalise_categories(db.connection())
        db.commit()

        assert _used(db, uid) == {"Milk": 4, "Bread": 1}
        assert _used(db, other) == {"milk": 3}
        budgets = {b.category: float(b.amount) for b in db.query(models.Budget).filter(models.Budget.user_id == uid)}
        assert budgets == {"Milk": 100.0, "__total_monthly__": 9000.0}  # the listed spelling's budget is kept
        assert db.query(models.RecurringTemplate).filter(models.RecurringTemplate.user_id == uid).one().category == "Milk"
        row = db.query(models.UserOptions).filter(models.UserOptions.user_id == uid).one()
        assert row.categories == ["Bread", "Milk"]
        assert {k: sorted(v) for k, v in row.subcategories.items()} == {"Milk": ["Cream", "Dairy"], "Bread": ["Rye"]}
        assert stats["expenses"] >= 2 and stats["recurring"] >= 1  # (the test database is shared)

        again = normalise_categories(db.connection())
        assert again == {"expenses": 0, "recurring": 0, "budgets": 0, "options": 0}  # nothing left to repair
    finally:
        db.close()


def test_repair_keeps_the_listed_spelling_even_when_another_is_used_more(client, make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _legacy(db, uid, "Milk", 5)
        _legacy(db, uid, "milk", 1)
        db.execute(sa.insert(models.UserOptions.__table__).values(user_id=uid, categories=["milk"], subcategories={}, units=[], shops=[], base_currency="SEK")) if not db.query(models.UserOptions).filter(models.UserOptions.user_id == uid).first() else db.execute(sa.update(models.UserOptions.__table__).where(models.UserOptions.user_id == uid).values(categories=["milk"]))
        db.commit()

        normalise_categories(db.connection())
        db.commit()

        assert _used(db, uid) == {"milk": 6}
    finally:
        db.close()


def test_repair_without_a_listed_spelling_uses_the_most_used_then_the_capitalised_one(client, make_user):
    a, _ = make_user()
    b, _ = make_user()
    db = SessionLocal()
    try:
        for uid in (a, b):
            db.query(models.UserOptions).filter(models.UserOptions.user_id == uid).delete()
        _legacy(db, a, "snacks", 3)
        _legacy(db, a, "Snacks", 1)
        _legacy(db, b, "snacks", 2)
        _legacy(db, b, "Snacks", 2)
        db.commit()

        normalise_categories(db.connection())
        db.commit()

        assert _used(db, a) == {"snacks": 4}
        assert _used(db, b) == {"Snacks": 4}
    finally:
        db.close()


def test_repair_also_fixes_expenses_a_user_added_to_a_shared_space(client, make_user):
    uid, h = make_user()
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    db = SessionLocal()
    try:
        _legacy(db, uid, "Milk", 2)
        _legacy(db, uid, "milk", 1, group_id=gid)
        db.commit()

        normalise_categories(db.connection())
        db.commit()

        assert _used(db, uid) == {"Milk": 3}
    finally:
        db.close()
