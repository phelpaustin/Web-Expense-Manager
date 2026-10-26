"""Period comparison: a month against last month, the same month last year and the 3-month average."""
import datetime as dt
from decimal import Decimal as D

from app.logic import period_compare as pc

TODAY = dt.date(2026, 10, 16)  # October 2026 is in progress


def e(date, amount, category="Food"):
    return {"date": dt.date.fromisoformat(date), "category": category, "amount": D(str(amount))}


HISTORY = [
    e("2025-09-10", 1000),                                  # September last year
    e("2026-06-05", 800), e("2026-07-05", 1000), e("2026-08-05", 1200),
    e("2026-09-05", 1500), e("2026-09-20", 500),            # September 2026 = 2000
]


def by_key(result):
    return {c["key"]: c for c in result["comparisons"]}


def test_compares_with_last_month_last_year_and_the_average():
    r = pc.period_compare(HISTORY, "2026-09", today=TODAY)
    c = by_key(r)
    assert r["total"] == D("2000.00") and r["partial"] is False
    assert (c["last_month"]["month"], c["last_month"]["before"], c["last_month"]["change"]) == ("2026-08", D("1200.00"), D("800.00"))
    assert c["last_month"]["pct_change"] == 66.7 and c["last_month"]["direction"] == "up"
    assert (c["last_year"]["month"], c["last_year"]["before"], c["last_year"]["pct_change"]) == ("2025-09", D("1000.00"), 100.0)
    # the three months before September: June, July and August
    assert c["average"]["months"] == ["2026-08", "2026-07", "2026-06"]
    assert c["average"]["before"] == D("1000.00") and c["average"]["change"] == D("1000.00")


def test_down_and_flat():
    r = pc.period_compare([e("2026-08-01", 500), e("2026-09-01", 400), e("2026-07-01", 400)], "2026-09", today=TODAY)
    c = by_key(r)
    assert c["last_month"]["direction"] == "down" and c["last_month"]["change"] == D("-100.00")
    assert c["average"]["before"] == D("450.00")  # July and August (June is before the first expense)
    flat = pc.period_compare([e("2026-08-01", 400), e("2026-09-01", 400)], "2026-09", today=TODAY)
    assert by_key(flat)["last_month"]["direction"] == "flat"


def test_no_history_is_not_a_spend_of_zero():
    r = pc.period_compare([e("2026-09-01", 400)], "2026-09", today=TODAY)
    c = by_key(r)
    for key in ("last_month", "last_year", "average"):
        assert c[key]["available"] is False and c[key]["before"] is None and c[key]["pct_change"] is None


def test_a_gap_inside_the_history_counts_as_zero():
    r = pc.period_compare([e("2026-06-01", 300), e("2026-09-01", 300)], "2026-09", today=TODAY)
    c = by_key(r)
    assert c["last_month"]["available"] is True and c["last_month"]["before"] == D("0.00")
    assert c["last_month"]["pct_change"] is None  # nothing before to take a percentage of
    assert c["average"]["before"] == D("100.00")   # June 300, July 0, August 0


def test_the_average_uses_fewer_months_when_there_are_fewer():
    r = pc.period_compare([e("2026-08-01", 600), e("2026-09-01", 300)], "2026-09", today=TODAY)
    assert by_key(r)["average"]["months"] == ["2026-08"] and by_key(r)["average"]["before"] == D("600.00")


def test_the_month_in_progress_is_compared_like_for_like():
    rows = [
        e("2026-09-02", 100), e("2026-09-25", 9999),         # September: only up to the 16th counts
        e("2026-10-03", 150), e("2026-10-20", 7777),         # a future date this month: left out
        e("2025-10-10", 100), e("2025-10-28", 5000),
        e("2026-07-01", 100), e("2026-08-01", 100),
    ]
    r = pc.period_compare(rows, "2026-10", today=TODAY)
    c = by_key(r)
    assert r["partial"] is True and r["through_day"] == 16 and r["total"] == D("150.00")
    assert c["last_month"]["before"] == D("100.00")
    assert c["last_year"]["before"] == D("100.00")
    assert c["average"]["before"] == D("100.00")  # July 100, August 100, September 100 (to the 16th)


def test_empty_data():
    r = pc.period_compare([], "2026-09", today=TODAY)
    assert r["total"] == D("0.00") and r["months"] == ["2026-09"]
    assert not any(c["available"] for c in r["comparisons"])


def test_default_month_is_the_last_finished_one():
    assert pc.default_month(HISTORY, today=TODAY) == "2026-09"


def test_months_for_the_picker_newest_first():
    assert pc.period_compare(HISTORY, "2026-09", today=TODAY)["months"][:3] == ["2026-09", "2026-08", "2026-07"]


def test_last_year_across_the_year_boundary():
    assert pc.same_month_last_year("2026-01") == "2025-01"
