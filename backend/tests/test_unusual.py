"""Unusual spending and possible duplicates."""
import datetime as dt
from decimal import Decimal as D

from app.logic import unusual as un

TODAY = dt.date(2026, 10, 16)
_next_id = iter(range(1, 10_000))


def e(date, amount, category="Food", description="x", shop="", **extra):
    return {"id": next(_next_id), "date": dt.date.fromisoformat(date), "category": category, "description": description, "shop": shop,
            "amount": D(str(amount)), "recurring_template_id": None, "source_bill_id": None, **extra}


def usual_food(n=10, amount=100):
    """n ordinary Food expenses, spread over the previous months."""
    return [e(f"2026-0{1 + i % 8}-1{i % 9}", amount + (i % 3) * 5) for i in range(n)]


def run(rows, **kw):
    return un.unusual_expenses(rows, today=TODAY, **kw)


def test_a_far_bigger_than_usual_expense_is_flagged():
    big = e("2026-10-10", 450, description="Dinner out")
    r = run(usual_food() + [big])
    [i] = r["items"]
    assert i["id"] == big["id"] and i["amount"] == D("450.00") and i["usual"] == D("105.00") and i["ratio"] == 4.3
    assert (i["category"], i["description"], i["date"], i["compared_with"]) == ("Food", "Dinner out", "2026-10-10", 10)
    assert r["total_found"] == 1 and r["checked"] == 1


def test_an_ordinary_or_slightly_bigger_expense_is_not():
    assert run(usual_food() + [e("2026-10-10", 110)])["items"] == []
    assert run(usual_food() + [e("2026-10-10", 200)])["items"] == []        # under 3 times the usual


def test_it_must_also_be_above_the_normal_range_not_just_three_times_the_median():
    wide = [e(f"2026-0{1 + i % 8}-1{i % 9}", a) for i, a in enumerate([10, 12, 15, 20, 90, 100, 110, 400, 420, 450])]
    r = run(wide + [e("2026-10-10", 400)])                                    # >3x the median, but inside this category's range
    assert r["items"] == []


def test_a_category_needs_enough_history_before_anything_is_judged():
    assert run(usual_food(7) + [e("2026-10-10", 5000)])["items"] == []
    assert run(usual_food(7) + [e("2026-10-10", 5000)])["checked"] == 0
    assert len(run(usual_food(7) + [e("2026-10-10", 5000)], min_history=7)["items"]) == 1


def test_only_recent_expenses_are_judged_but_old_ones_still_count_as_history():
    old_big = e("2026-08-01", 900)
    assert run(usual_food() + [old_big])["items"] == []
    assert len(run(usual_food() + [old_big], recent_days=90)["items"]) == 1


def test_history_older_than_a_year_is_left_out():
    ancient = [e("2023-03-03", 5000) for _ in range(10)]                    # would make 450 look ordinary
    assert len(run(ancient + usual_food() + [e("2026-10-10", 450)])["items"]) == 1
    assert run(ancient + usual_food() + [e("2026-10-10", 450)], history_months=0)["items"] == []


def test_categories_are_judged_separately_ignoring_case():
    rows = usual_food() + [e("2026-10-10", 450, category="Travel")]
    assert run(rows)["items"] == []                                         # Travel has no history
    rows = usual_food() + [e("2026-10-10", 450, category="food")]
    assert len(run(rows)["items"]) == 1


def test_payments_from_a_recurring_template_are_never_flagged():
    assert run(usual_food() + [e("2026-10-10", 450, recurring_template_id=7)])["items"] == []


def test_future_dates_zero_amounts_and_bad_dates_are_ignored():
    rows = usual_food() + [e("2026-11-20", 450), e("2026-10-10", 0), {**e("2026-10-10", 450), "date": "not a date"}]
    assert run(rows)["items"] == []


def test_the_biggest_ratio_comes_first_and_only_the_top_are_returned():
    rows = usual_food() + [e("2026-10-01", 450), e("2026-10-02", 900), e("2026-10-03", 600)]
    assert [i["amount"] for i in run(rows)["items"]] == [D("900.00"), D("600.00"), D("450.00")]
    top = run(rows, top=2)
    assert len(top["items"]) == 2 and top["total_found"] == 3


def test_an_uncategorised_expense_is_judged_with_the_other_uncategorised_ones():
    rows = [e(f"2026-0{1 + i % 8}-1{i % 9}", 100, category="") for i in range(10)] + [e("2026-10-10", 500, category=None)]
    [i] = run(rows)["items"]
    assert i["category"] == "Uncategorised"


# --- possible duplicates -----------------------------------------------------------------------

def dup(rows, **kw):
    return un.possible_duplicates(rows, today=TODAY, **kw)


def test_the_same_entry_twice_is_a_possible_duplicate():
    a, b = e("2026-10-10", 59.9, description="Lunch", shop="Max"), e("2026-10-10", 59.9, description="lunch ", shop="MAX")
    r = dup([a, b, e("2026-10-10", 59.9, description="Lunch", shop="Other")])
    [d] = r["items"]
    assert d["count"] == 2 and d["amount"] == D("59.90") and d["date"] == "2026-10-10" and d["ids"] == sorted([a["id"], b["id"]])
    assert d["description"] == "Lunch" and d["shop"] == "Max" and r["total_found"] == 1


def test_different_amount_day_or_category_is_not_a_duplicate():
    base = e("2026-10-10", 50, description="Lunch", shop="Max")
    assert dup([base, e("2026-10-10", 51, description="Lunch", shop="Max")])["items"] == []
    assert dup([base, e("2026-10-11", 50, description="Lunch", shop="Max")])["items"] == []
    assert dup([base, e("2026-10-10", 50, description="Lunch", shop="Max", category="Work")])["items"] == []


def test_the_same_item_twice_on_one_bill_is_not_a_mistake():
    rows = [e("2026-10-10", 20, description="Milk", shop="ICA", source_bill_id=5), e("2026-10-10", 20, description="Milk", shop="ICA", source_bill_id=5)]
    assert dup(rows)["items"] == []
    rows.append(e("2026-10-10", 20, description="Milk", shop="ICA"))                  # also typed in by hand
    assert dup(rows)["items"][0]["count"] == 2


def test_two_bills_with_the_same_line_are_two_entries():
    rows = [e("2026-10-10", 20, description="Milk", shop="ICA", source_bill_id=5), e("2026-10-10", 20, description="Milk", shop="ICA", source_bill_id=6)]
    assert dup(rows)["items"][0]["count"] == 2


def test_three_copies_are_one_group_of_three():
    rows = [e("2026-10-10", 20, description="Milk", shop="ICA") for _ in range(3)]
    assert [d["count"] for d in dup(rows)["items"]] == [3]


def test_entries_with_neither_a_description_nor_a_shop_are_not_compared():
    assert dup([e("2026-10-10", 20, description="", shop=""), e("2026-10-10", 20, description="", shop="")])["items"] == []
    assert len(dup([e("2026-10-10", 20, description="", shop="Max"), e("2026-10-10", 20, description="", shop="Max")])["items"]) == 1


def test_only_recent_entries_are_looked_at_and_the_newest_come_first():
    old = [e("2026-06-01", 20, description="Milk", shop="ICA") for _ in range(2)]
    new1 = [e("2026-10-01", 30, description="Eggs", shop="ICA") for _ in range(2)]
    new2 = [e("2026-10-09", 10, description="Bread", shop="ICA") for _ in range(2)]
    r = dup(old + new1 + new2)
    assert [d["description"] for d in r["items"]] == ["Bread", "Eggs"]
    assert len(dup(old + new1 + new2, recent_days=200)["items"]) == 3
    assert len(dup(old + new1 + new2, top=1)["items"]) == 1 and dup(old + new1 + new2, top=1)["total_found"] == 2


def test_future_dated_pairs_are_ignored():
    assert dup([e("2026-11-20", 20, description="Milk", shop="ICA") for _ in range(2)])["items"] == []


def test_only_the_bills_the_caller_calls_receipts_group_their_lines():
    rows = [e("2026-10-10", 20, description="Milk", shop="ICA", source_bill_id=5), e("2026-10-10", 20, description="Milk", shop="ICA", source_bill_id=5)]
    seen = []
    def receipts(ids):
        seen.append(ids)
        return set()                                                    # bill 5 is a derived bill, not a receipt
    assert dup(rows, receipt_bills=receipts)["items"][0]["count"] == 2
    assert seen == [{5}]
    assert dup(rows, receipt_bills=lambda ids: {5})["items"] == []      # bill 5 is a receipt


def test_the_bill_lookup_is_only_made_for_lookalikes():
    calls = []
    dup([e("2026-10-10", 20, description="A", shop="x", source_bill_id=1), e("2026-10-10", 21, description="B", shop="x", source_bill_id=2)],
        receipt_bills=lambda ids: calls.append(ids) or set())
    assert calls == []


# ── "not a duplicate" ──

def two_lunches(day="2026-10-10", amount=60, **extra):
    return [e(day, amount, description="Lunch", shop="Max", **extra), e(day, amount, description="Lunch", shop="Max", **extra)]


def test_each_group_has_a_stable_key():
    [a] = dup(two_lunches())["items"]
    assert len(a["key"]) == 64 and set(a["key"]) <= set("0123456789abcdef")
    assert dup(two_lunches())["items"][0]["key"] == a["key"]                                 # same entries, same key
    assert dup(two_lunches(amount=61))["items"][0]["key"] != a["key"]
    assert dup(two_lunches(day="2026-10-11"))["items"][0]["key"] != a["key"]
    assert dup([e("2026-10-10", 60, description="Lunch", shop="Max "), e("2026-10-10", 60, description="LUNCH", shop="max")])["items"][0]["key"] == a["key"]
    assert un.duplicate_key(dt.date(2026, 10, 10), D("60"), "lunch", "max", "food") == a["key"]


def test_a_group_nobody_dismissed_is_not_marked():
    r = dup(two_lunches())
    assert r["items"][0]["was_dismissed"] is False and r["dismissed"] == [] and r["dismissed_total"] == 0


def test_a_dismissed_group_leaves_the_list_and_is_reported_separately():
    key = dup(two_lunches())["items"][0]["key"]
    r = dup(two_lunches(), dismissed={key: 2})
    assert r["items"] == [] and r["total_found"] == 0
    assert [d["key"] for d in r["dismissed"]] == [key] and r["dismissed_total"] == 1 and r["dismissed"][0]["count"] == 2


def test_one_more_lookalike_brings_a_dismissed_group_back():
    key = dup(two_lunches())["items"][0]["key"]
    r = dup(two_lunches() + [e("2026-10-10", 60, description="Lunch", shop="Max")], dismissed={key: 2})
    [item] = r["items"]
    assert item["count"] == 3 and item["was_dismissed"] is True and r["dismissed"] == []
    assert dup(two_lunches() + [e("2026-10-10", 60, description="Lunch", shop="Max")], dismissed={key: 3})["items"] == []


def test_a_dismissal_with_a_bigger_count_still_hides_a_group_that_shrank():
    key = dup(two_lunches())["items"][0]["key"]
    assert dup(two_lunches(), dismissed={key: 5})["items"] == []


def test_a_dismissal_only_covers_its_own_group():
    other = dup(two_lunches(amount=75))["items"][0]["key"]
    r = dup(two_lunches() + two_lunches(amount=75, day="2026-10-12"), dismissed={other: 2})
    assert len(r["items"]) == 2                                          # a different day makes a different group
    assert dup(two_lunches() + two_lunches(amount=75), dismissed={other: 2})["items"][0]["amount"] == D("60.00")


def test_dismissals_that_match_nothing_are_ignored():
    r = dup(two_lunches(), dismissed={"0" * 64: 2, "f" * 64: 9})
    assert len(r["items"]) == 1 and r["dismissed"] == []


def test_both_lists_are_cut_to_top():
    rows, keys = [], {}
    for d in range(1, 6):
        rows += two_lunches(day=f"2026-10-0{d}")
        keys[dup(two_lunches(day=f"2026-10-0{d}"))["items"][0]["key"]] = 2
    shown = [k for i, k in enumerate(keys) if i < 3]
    r = dup(rows, top=2, dismissed={k: 2 for k in shown})
    assert len(r["items"]) == 2 and r["total_found"] == 2 and len(r["dismissed"]) == 2 and r["dismissed_total"] == 3


def test_an_old_dismissal_does_not_hide_a_group_outside_the_window_either_way():
    old = two_lunches(day="2026-06-01")
    assert dup(old)["items"] == []                                       # outside the 60 days anyway
    key = un.duplicate_key(dt.date(2026, 6, 1), D("60"), "lunch", "max", "food")
    assert dup(old, dismissed={key: 2})["dismissed"] == []
