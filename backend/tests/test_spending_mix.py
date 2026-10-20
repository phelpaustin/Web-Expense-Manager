"""Committed vs everyday vs one-off spending, month by month."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.logic import spending_mix as sm

TODAY = dt.date(2026, 10, 16)


def e(date, category, amount, **extra):
    return {"id": extra.pop("id", None), "date": dt.date.fromisoformat(date), "category": category, "amount": D(str(amount)),
            "description": extra.pop("description", category), "shop": "", **extra}


def ordinary(category="Groceries", n=9, amounts=(100, 120, 140, 160, 180)):
    """n everyday purchases spread over June to September 2026."""
    months = ("2026-06", "2026-07", "2026-08", "2026-09")
    return [e(f"{months[i % 4]}-{10 + i:02d}", category, amounts[i % len(amounts)]) for i in range(n)]


def mix(rows, **kw):
    return sm.spending_mix(rows, today=TODAY, **kw)


def month(result, key):
    return next(m for m in result["months"] if m["month"] == key)


# --- the one-off rule ----------------------------------------------------------------------

def test_a_purchase_far_above_the_usual_for_its_category_is_a_one_off():
    rows = ordinary() + [e("2026-09-20", "Groceries", 2500, id=77, description="Party catering")]

    r = mix(rows)

    [o] = r["one_offs"]
    assert (o["id"], o["description"], o["amount"], o["basis"]) == (77, "Party catering", D("2500.00"), "category")
    assert o["usual"] == D("140.00") and o["ratio"] == 17.9
    assert month(r, "2026-09")["one_off"] == D("2500.00")
    assert r["one_off_count"] == 1


def test_ordinary_and_merely_larger_purchases_are_not_one_offs():
    # 280 is twice the usual 140: well short of three times.
    r = mix(ordinary() + [e("2026-09-20", "Groceries", 280)])

    assert r["one_offs"] == [] and r["totals"]["one_off"] == D("0.00")


def test_the_boundary_is_strictly_above_three_times_when_every_purchase_is_alike():
    same = [e(f"2026-09-{d:02d}", "Cola", 100) for d in range(1, 9)]  # usual 100, spread none: threshold is 300

    assert mix(same + [e("2026-09-20", "Cola", 300)])["one_offs"] == []
    assert [o["amount"] for o in mix(same + [e("2026-09-20", "Cola", 301)])["one_offs"]] == [D("301.00")]


def test_a_few_big_purchases_do_not_hide_themselves():
    # Two huge purchases among ten: the median, unlike the average, still says ~100.
    rows = [e(f"2026-09-{d:02d}", "Home", 100) for d in range(1, 9)] + [e("2026-09-20", "Home", 5000), e("2026-09-21", "Home", 6000)]

    assert sorted(o["amount"] for o in mix(rows)["one_offs"]) == [D("5000.00"), D("6000.00")]


def test_a_category_where_big_purchases_are_normal_is_not_flagged():
    travel = [e(f"2026-0{m}-05", "Travel", a) for m, a in zip((1, 2, 3, 4, 5, 6, 7, 8, 9), (2000, 2500, 1800, 3000, 2200, 2800, 2100, 2600, 2400))]

    assert mix(travel)["one_offs"] == []


def test_a_category_with_too_little_history_is_judged_against_everything_you_buy():
    rows = ordinary("Groceries", 10) + [e("2026-09-25", "Electronics", 3000, description="Laptop")]

    [o] = mix(rows)["one_offs"]

    assert (o["description"], o["basis"]) == ("Laptop", "overall")
    assert o["usual"] == D("140.00")


def test_with_too_little_history_overall_nothing_is_judged():
    rows = ordinary("Groceries", 4) + [e("2026-09-25", "Electronics", 99999)]

    r = mix(rows)

    assert r["one_offs"] == [] and r["totals"]["one_off"] == D("0.00")


def test_usual_is_measured_over_the_last_year_not_just_the_months_shown():
    history = [e(f"2025-12-{d:02d}", "Groceries", 100) for d in range(1, 10)]      # well before the one month shown
    rows = history + [e("2026-10-05", "Groceries", 900)]

    r = mix(rows, months=1)

    assert [o["amount"] for o in r["one_offs"]] == [D("900.00")]
    assert r["months"] == [month(r, "2026-10")] and len(r["months"]) == 1


def test_history_older_than_a_year_does_not_count_towards_usual():
    old_expensive = [e(f"2025-06-{d:02d}", "Groceries", 5000) for d in range(1, 10)]   # 16 months ago
    recent = [e(f"2026-09-{d:02d}", "Groceries", 100) for d in range(1, 9)]

    r = mix(old_expensive + recent + [e("2026-10-01", "Groceries", 900)])

    assert [o["amount"] for o in r["one_offs"]] == [D("900.00")]


# --- committed spending --------------------------------------------------------------------

def test_a_large_recurring_payment_is_committed_never_a_one_off():
    rows = ordinary() + [e("2026-09-01", "Housing", 9000, recurring_template_id=3, description="Rent"),
                         e("2026-08-01", "Housing", 9000, recurring_template_id=3, description="Rent")]

    r = mix(rows)

    assert r["one_offs"] == []
    assert month(r, "2026-09")["committed"] == D("9000.00") and month(r, "2026-08")["committed"] == D("9000.00")


def test_committed_payments_do_not_shape_what_is_usual_for_a_category():
    ordinary_rows = [e(f"2026-09-{d:02d}", "Groceries", 100) for d in range(1, 9)]
    committed = [e(f"2026-08-{d:02d}", "Groceries", 10000, recurring_template_id=1) for d in range(1, 10)]

    r = mix(ordinary_rows + committed + [e("2026-09-20", "Groceries", 500)])

    assert [o["amount"] for o in r["one_offs"]] == [D("500.00")]  # judged against 100, not against the 10,000s


def test_the_biggest_commitments_are_listed_by_template():
    rows = [e("2026-08-01", "Housing", 9000, recurring_template_id=3, description="Rent"),
            e("2026-09-01", "Housing", 9000, recurring_template_id=3, description="Rent"),
            e("2026-09-02", "Media", 120, recurring_template_id=5, description="Streaming"),
            e("2026-10-02", "Media", 120, recurring_template_id=5, description="streaming"),
            e("2026-10-03", "Media", 120, recurring_template_id=5, description="Streaming")]

    top = mix(rows)["committed_top"]

    assert [(c["template_id"], c["description"], c["total"], c["count"], c["last_date"]) for c in top] == [
        (3, "Rent", D("18000.00"), 2, "2026-09-01"), (5, "Streaming", D("360.00"), 3, "2026-10-03")]


# --- the monthly arithmetic ----------------------------------------------------------------

def test_the_three_parts_of_every_month_add_up_to_its_total():
    rows = ordinary() + [e("2026-09-20", "Groceries", 2500), e("2026-09-01", "Housing", 9000, recurring_template_id=3),
                         e("2026-10-02", "Fun", "12.345")]

    r = mix(rows)

    for m in r["months"]:
        assert m["committed"] + m["everyday"] + m["one_off"] == m["total"]
    assert sum(m["total"] for m in r["months"]) == r["totals"]["total"]
    assert r["totals"]["total"] == r["totals"]["committed"] + r["totals"]["everyday"] + r["totals"]["one_off"]


def test_the_window_has_every_month_including_quiet_ones_and_marks_the_current_one():
    r = mix([e("2026-03-05", "Food", 50), e("2026-10-05", "Food", 70)], months=8)

    assert [m["month"] for m in r["months"]] == ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert month(r, "2026-05")["total"] == D("0.00")
    assert [m["partial"] for m in r["months"]] == [False] * 7 + [True]
    assert r["window"] == {"from": "2026-03-01", "to": "2026-10-16", "months": 8}


def test_the_window_is_between_one_and_twelve_months():
    assert len(mix([], months=0)["months"]) == 1
    assert len(mix([], months=99)["months"]) == 12
    assert mix([], months=12)["months"][0]["month"] == "2025-11"


def test_a_typical_month_averages_the_finished_months_since_recording_began():
    rows = [e("2026-07-05", "Food", 100), e("2026-08-05", "Food", 200), e("2026-09-05", "Food", 300),
            e("2026-08-01", "Housing", 1000, recurring_template_id=1), e("2026-09-01", "Housing", 1000, recurring_template_id=1),
            e("2026-10-05", "Food", 1)]  # the month in progress is left out

    t = mix(rows)["typical"]

    assert t["months"] == 3                                    # July to September: nothing before July
    assert (t["committed"], t["everyday"], t["one_off"]) == (D("666.67"), D("200.00"), D("0.00"))
    assert t["baseline"] == D("866.67") and t["total"] == D("866.67")


def test_a_typical_month_needs_at_least_two_finished_months():
    assert mix([e("2026-09-05", "Food", 100), e("2026-10-05", "Food", 100)])["typical"] is None
    assert mix([e("2026-08-05", "Food", 100), e("2026-09-05", "Food", 100)])["typical"]["months"] == 2


def test_shares_of_the_total():
    r = mix([e("2026-09-01", "Housing", 600, recurring_template_id=1), e("2026-09-05", "Food", 400)])

    assert (r["totals"]["committed_pct"], r["totals"]["one_off_pct"]) == (60.0, 0.0)


def test_nothing_recorded_is_unavailable_not_an_error():
    r = mix([])

    assert r["available"] is False and r["typical"] is None and r["one_offs"] == [] and r["committed_top"] == []
    assert r["totals"]["total"] == D("0.00") and r["totals"]["committed_pct"] is None
    assert mix([e("2020-01-01", "Food", 10)])["available"] is False  # nothing inside the window


# --- the biggest one-offs ------------------------------------------------------------------

def test_one_offs_are_listed_biggest_first_limited_to_top_and_all_are_counted():
    big = [e(f"2026-09-{d:02d}", "Groceries", a, description=f"big{a}") for d, a in zip(range(1, 6), (1000, 3000, 2000, 5000, 4000))]

    r = mix(ordinary() + big, top=3)

    assert [o["description"] for o in r["one_offs"]] == ["big5000", "big4000", "big3000"]
    assert r["one_off_count"] == 5 and r["totals"]["one_off"] == D("15000.00")


def test_equal_amounts_are_ordered_by_date_for_a_stable_list():
    rows = ordinary() + [e("2026-09-25", "Groceries", 2000, description="later"), e("2026-09-02", "Groceries", 2000, description="earlier")]

    assert [o["description"] for o in mix(rows)["one_offs"]] == ["earlier", "later"]


# --- awkward rows --------------------------------------------------------------------------

def test_unusable_rows_are_ignored_and_a_missing_link_means_not_committed():
    rows = ordinary() + [e("2026-10-17", "Groceries", 9999),                      # tomorrow
                         e("2026-09-02", "Groceries", 0), e("2026-09-02", "Groceries", -50),
                         {"date": None, "category": "Food", "amount": D(5)}, {"date": "garbage", "category": "Food", "amount": D(5)},
                         {"date": "2026-09-03", "category": "Food", "amount": "7.5"}]   # text date and amount are fine

    r = mix(rows)

    assert r["one_offs"] == []
    # September's ordinary purchases are 160 + 140; the text-dated 7.50 counts too, nothing else does.
    assert month(r, "2026-09")["everyday"] == D("307.50")


def test_rows_are_not_modified():
    rows = ordinary()
    before = [dict(r) for r in rows]

    mix(rows)

    assert rows == before


def test_blank_categories_are_one_group():
    blanks = [e(f"2026-09-{d:02d}", "", 100) for d in range(1, 9)] + [e("2026-09-20", None, 2000)]

    assert [o["amount"] for o in mix(blanks)["one_offs"]] == [D("2000.00")]


def test_the_rule_is_published_for_the_ui():
    assert mix([])["rule"] == {"min_samples": 8, "multiple": 3, "sigmas": 3}
