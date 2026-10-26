"""Biggest movers: categories and shops that rose, fell or are new against the month before."""
import datetime as dt
from decimal import Decimal as D

from app.logic import movers as mv

TODAY = dt.date(2026, 10, 16)  # October 2026 is in progress


def e(date, amount, category="Food", shop=""):
    return {"date": dt.date.fromisoformat(date), "category": category, "shop": shop, "amount": D(str(amount))}


def names(rows):
    return [r["name"] for r in rows]


SEPT = [
    e("2026-08-05", 500, "Food", "Lidl"), e("2026-08-06", 300, "Fun", "Cinema"), e("2026-08-07", 100, "Travel", "SJ"),
    e("2026-08-08", 50, "Health", "Apotek"),
    e("2026-09-05", 900, "Food", "Lidl"), e("2026-09-06", 100, "Fun", "Cinema"),
    e("2026-09-07", 250, "Pets", "Zoo"), e("2026-09-08", 20, "Health", "Apotek"),
]


def test_rose_fell_and_new_are_told_apart():
    r = mv.movers(SEPT, "2026-09", today=TODAY)
    c = r["categories"]
    assert names(c["rose"]) == ["Food"] and c["rose"][0]["change"] == D("400.00") and c["rose"][0]["pct_change"] == 80.0
    assert names(c["fell"]) == ["Fun", "Travel", "Health"]
    assert names(c["new"]) == ["Pets"] and c["new"][0]["status"] == "new" and c["new"][0]["pct_change"] is None
    assert r["available"] is True and r["compare_month"] == "2026-08" and r["partial"] is False


def test_fell_is_sorted_by_size_of_the_fall():
    r = mv.movers(SEPT, "2026-09", today=TODAY)
    fell = r["categories"]["fell"]
    assert [f["change"] for f in fell] == sorted(f["change"] for f in fell)  # most negative first
    assert fell[0]["name"] == "Fun" and fell[0]["change"] == D("-200.00")
    stopped = next(f for f in fell if f["name"] == "Travel")
    assert stopped["status"] == "stopped" and stopped["now"] == D("0.00")


def test_a_new_one_is_not_also_a_rise():
    r = mv.movers(SEPT, "2026-09", today=TODAY)
    assert "Pets" not in names(r["categories"]["rose"])


def test_shops_are_listed_the_same_way_and_a_blank_shop_is_left_out():
    rows = SEPT + [e("2026-09-09", 700, "Food", ""), e("2026-08-09", 10, "Food", "")]
    r = mv.movers(rows, "2026-09", today=TODAY)
    s = r["shops"]
    assert names(s["rose"]) == ["Lidl"] and names(s["new"]) == ["Zoo"] and "" not in names(s["fell"]) + names(s["rose"]) + names(s["new"])
    assert names(s["fell"])[0] == "Cinema"


def test_only_the_top_few_are_returned():
    rows = [e("2026-08-01", 100, f"C{i}") for i in range(6)] + [e("2026-09-01", 100 + 10 * (i + 1), f"C{i}") for i in range(6)]
    r = mv.movers(rows, "2026-09", today=TODAY, top=2)
    assert names(r["categories"]["rose"]) == ["C5", "C4"]
    assert len(mv.movers(rows, "2026-09", today=TODAY)["categories"]["rose"]) == 3


def test_nothing_before_means_nothing_to_compare_not_all_new():
    r = mv.movers([e("2026-09-01", 100)], "2026-09", today=TODAY)
    assert r["available"] is False


def test_a_gap_month_in_the_history_still_has_something_to_compare_with():
    r = mv.movers([e("2026-06-01", 100, "Food"), e("2026-09-01", 100, "Food")], "2026-09", today=TODAY)
    assert r["available"] is True and names(r["categories"]["new"]) == ["Food"]


def test_uncategorised_gets_a_name():
    r = mv.movers([e("2026-08-01", 10, "Food"), e("2026-09-01", 50, "")], "2026-09", today=TODAY)
    assert names(r["categories"]["new"]) == ["Uncategorised"]


def test_the_month_in_progress_is_compared_like_for_like():
    rows = [
        e("2026-09-02", 100, "Food"), e("2026-09-25", 9999, "Food"),   # September: only to the 16th counts
        e("2026-10-03", 150, "Food"), e("2026-10-20", 7777, "Food"),   # a later date this month is left out
    ]
    r = mv.movers(rows, "2026-10", today=TODAY)
    assert r["partial"] is True and r["through_day"] == 16
    food = r["categories"]["rose"][0]
    assert food["now"] == D("150.00") and food["before"] == D("100.00")


def test_the_month_list_includes_the_chosen_month_newest_first():
    r = mv.movers(SEPT, "2026-10", today=TODAY)
    assert r["months"] == ["2026-10", "2026-09", "2026-08"]
