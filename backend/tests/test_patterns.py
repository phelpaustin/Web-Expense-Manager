"""Spending patterns: weekdays and parts of the month."""
import datetime as dt
from decimal import Decimal as D

from app.logic import patterns as pt

TODAY = dt.date(2026, 10, 16)          # a Friday; the 6-month window starts on 2026-04-01 (a Wednesday)


def e(date, amount, **extra):
    return {"date": dt.date.fromisoformat(date), "amount": D(str(amount)), "recurring_template_id": None, **extra}


def spread(n=30, amount=10, start=dt.date(2026, 9, 1)):
    return [e((start + dt.timedelta(days=i)).isoformat(), amount) for i in range(n)]


def run(rows, **kw):
    return pt.spending_patterns(rows, today=TODAY, **kw)


def test_the_window_counts_each_weekday_and_part_of_the_month():
    r = run([])
    assert (r["start"], r["end"], r["days"]) == ("2026-04-01", "2026-10-16", 199)
    assert sum(w["days"] for w in r["weekdays"]) == 199
    assert sum(p["days"] for p in r["month_parts"]) == 199
    assert [w["name"] for w in r["weekdays"]][:2] == ["Monday", "Tuesday"]
    assert [p["label"] for p in r["month_parts"]] == ["1–7", "8–14", "15–21", "22–31"]
    # Apr-Sep give 7 days to each of the first two parts and 6 x 7 + the 2 days of October (15, 16) to the third.
    assert [p["days"] for p in r["month_parts"]] == [49, 49, 44, 57]


def test_averages_are_per_calendar_day_not_per_expense():
    # One 140 expense on each Saturday in the window against nothing else.
    sat = [e(d.isoformat(), 140) for d in (dt.date(2026, 4, 1) + dt.timedelta(days=i) for i in range(199)) if d.weekday() == 5]
    r = run(sat * 1)
    w = r["weekdays"][5]
    assert w["total"] == D(140 * len(sat)).quantize(D("0.01")) and w["count"] == len(sat) == w["days"]
    assert w["per_day"] == D("140.00")
    assert r["weekdays"][0]["per_day"] == D("0.00")


def test_a_weekday_with_more_days_in_the_window_is_not_favoured():
    rows = [e("2026-10-05", 100), e("2026-10-06", 100)]   # a Monday and a Tuesday
    r = run(rows)
    mon, tue = r["weekdays"][0], r["weekdays"][1]
    assert mon["days"] != 0 and tue["days"] != 0
    assert mon["per_day"] == (D(100) / mon["days"]).quantize(D("0.01"))
    assert tue["per_day"] == (D(100) / tue["days"]).quantize(D("0.01"))


def test_the_parts_of_the_month_use_the_day_of_the_month():
    r = run([e("2026-10-03", 50), e("2026-10-08", 20), e("2026-10-15", 10), e("2026-09-22", 5), e("2026-09-30", 5)])
    totals = [p["total"] for p in r["month_parts"]]
    assert totals == [D("50.00"), D("20.00"), D("10.00"), D("10.00")]
    assert [p["count"] for p in r["month_parts"]] == [1, 1, 1, 2]
    assert [p["share_pct"] for p in r["month_parts"]] == [55.6, 22.2, 11.1, 11.1]


def test_recurring_payments_refunds_and_zero_amounts_are_left_out():
    rows = [e("2026-10-05", 100), e("2026-10-05", 900, recurring_template_id=3), e("2026-10-05", -40), e("2026-10-05", 0)]
    r = run(rows)
    assert (r["count"], r["spent"]) == (1, D("100.00"))
    assert run(rows, include_recurring=True)["spent"] == D("1000.00")


def test_expenses_outside_the_window_are_ignored():
    r = run([e("2026-03-31", 100), e("2026-10-17", 100), e("2026-10-16", 7)])
    assert (r["count"], r["spent"]) == (1, D("7.00"))
    assert run([e("2026-03-31", 100)], months=7)["count"] == 1


def test_too_few_expenses_says_so_and_draws_no_conclusion():
    r = run(spread(5))
    assert r["enough"] is False and r["busiest_weekday"] is None and r["weekend"] is None
    assert len(r["weekdays"]) == 7 and r["count"] == 5          # the numbers are still there to show


def test_a_short_window_is_not_enough_even_with_many_expenses():
    r = run(spread(30) * 2, months=0)         # months=0 -> only this month so far (16 days)
    assert r["days"] == 16 and r["enough"] is False


def test_busiest_and_quietest_weekday_and_the_weekend():
    rows = []
    d = dt.date(2026, 4, 1)
    while d <= TODAY:
        if d.weekday() in (4, 5, 6):
            rows.append(e(d.isoformat(), 80 if d.weekday() == 5 else 40))
        else:
            rows.append(e(d.isoformat(), 5))
        d += dt.timedelta(days=1)
    r = run(rows)
    assert r["enough"] is True
    assert r["busiest_weekday"] == "Saturday"
    assert r["quietest_weekday"] in ("Monday", "Tuesday", "Wednesday", "Thursday")
    wk = r["weekend"]
    weekday_rows = [x for x in rows if x["date"].weekday() < 5]
    expected_weekday_avg = (sum(x["amount"] for x in weekday_rows) / len(weekday_rows)).quantize(D("0.01"))
    assert wk["per_day"] == D("60.00")                      # Saturdays 80, Sundays 40
    assert wk["weekday_per_day"] == expected_weekday_avg    # Mon-Thu 5, Fri 40
    assert wk["ratio"] == round(float(D("60") / expected_weekday_avg), 1)


def test_ties_go_to_the_earlier_weekday_and_a_flat_week_has_a_ratio_of_one():
    rows = [e((dt.date(2026, 4, 1) + dt.timedelta(days=i)).isoformat(), 10) for i in range(199)]
    r = run(rows)
    assert r["busiest_weekday"] == "Monday" and r["quietest_weekday"] == "Sunday"
    assert r["weekend"]["ratio"] == 1.0 and r["weekend"]["per_day"] == D("10.00")


def test_amounts_are_decimals_and_shares_add_up():
    r = run(spread(30, amount="3.33"))
    assert all(isinstance(w["total"], D) and isinstance(w["per_day"], D) for w in r["weekdays"])
    assert abs(sum(w["share_pct"] for w in r["weekdays"]) - 100) < 0.5
    assert abs(sum(p["share_pct"] for p in r["month_parts"]) - 100) < 0.5
