"""Recurring costs: per month and per year, next due dates and price rises."""
import datetime as dt
from decimal import Decimal as D

from app.logic import recurring_costs as rc

TODAY = dt.date(2026, 10, 16)


def tpl(id, item, amount, frequency="Monthly", last_applied=None, anchor=None, native=None, cur="SEK"):
    return {"id": id, "item": item, "category": "Subs", "frequency": frequency, "amount": D(str(amount)),
            "native_amount": D(str(native if native is not None else amount)), "native_currency": cur,
            "last_applied": last_applied, "schedule_anchor": anchor}


def pay(template_id, date, amount, cur="SEK", id=None):
    return {"id": id, "template_id": template_id, "date": dt.date.fromisoformat(date), "amount": D(str(amount)), "currency": cur}


def test_cost_per_month_and_year_for_each_frequency():
    assert rc.monthly_cost(100, "Monthly") == D("100.00") and rc.yearly_cost(100, "Monthly") == D("1200.00")
    assert rc.yearly_cost(100, "Yearly") == D("100.00") and rc.monthly_cost(1200, "Yearly") == D("100.00")
    assert rc.monthly_cost(300, "Quarterly") == D("100.00")
    assert rc.yearly_cost(10, "Weekly") == D("520.00") and rc.monthly_cost(12, "Weekly") == D("52.00")
    assert rc.yearly_cost(10, "Bi-weekly") == D("260.00")
    assert rc.yearly_cost(1, "Daily") == D("365.00")
    assert rc.yearly_cost(100, "Fortnightly-ish") == D("1200.00")  # unknown counts as monthly, like the schedule


def test_totals_and_order_by_monthly_cost():
    r = rc.recurring_costs([tpl(1, "Gym", 300), tpl(2, "Insurance", 1200, "Yearly"), tpl(3, "Netflix", 150)], [], TODAY)
    assert [i["item"] for i in r["items"]] == ["Gym", "Netflix", "Insurance"]   # 300, 150, 100 a month
    assert r["count"] == 3 and r["monthly_total"] == D("550.00") and r["yearly_total"] == D("6600.00")
    assert r["price_rises"] == 0


def test_nothing_recurring():
    r = rc.recurring_costs([], [], TODAY)
    assert r == {"count": 0, "monthly_total": D("0.00"), "yearly_total": D("0.00"), "price_rises": 0, "items": []}


def test_next_due_and_overdue():
    r = rc.recurring_costs([
        tpl(1, "Paid", 100, last_applied=dt.date(2026, 10, 1)),
        tpl(2, "Late", 100, last_applied=dt.date(2026, 8, 20)),
        tpl(3, "Never", 100),
    ], [], TODAY)
    by = {i["item"]: i for i in r["items"]}
    assert by["Paid"]["next_due"] == dt.date(2026, 11, 1) and by["Paid"]["overdue"] is False
    assert by["Late"]["next_due"] == dt.date(2026, 9, 20) and by["Late"]["overdue"] is True
    assert by["Never"]["next_due"] == TODAY and by["Never"]["overdue"] is False


def test_next_due_for_day_based_and_month_end_schedules():
    from app.logic.recurring import next_due
    assert next_due(dt.date(2026, 10, 10), "Weekly", TODAY) == dt.date(2026, 10, 17)
    assert next_due(dt.date(2026, 1, 31), "Monthly", TODAY, schedule_anchor=dt.date(2026, 1, 31)) == dt.date(2026, 2, 28)
    assert next_due(dt.date(2026, 2, 28), "Monthly", TODAY, schedule_anchor=dt.date(2026, 1, 31)) == dt.date(2026, 3, 31)


def test_last_paid_and_payment_count():
    r = rc.recurring_costs([tpl(1, "Gym", 300)], [pay(1, "2026-08-01", 300), pay(1, "2026-09-01", 300), pay(9, "2026-09-02", 5)], TODAY)
    i = r["items"][0]
    assert i["last_paid"] == dt.date(2026, 9, 1) and i["payments"] == 2


def test_a_price_rise_is_spotted_and_dated():
    payments = [pay(1, "2026-07-01", 100, id=1), pay(1, "2026-08-01", 100, id=2), pay(1, "2026-09-01", 120, id=3), pay(1, "2026-10-01", 120, id=4)]
    r = rc.recurring_costs([tpl(1, "Netflix", 120)], payments, TODAY)
    c = r["items"][0]["price_change"]
    assert c["from"] == D("100.00") and c["to"] == D("120.00") and c["since"] == dt.date(2026, 9, 1)
    assert c["pct_change"] == 20.0 and c["direction"] == "up" and c["currency"] == "SEK"
    assert r["price_rises"] == 1


def test_a_price_fall_is_not_counted_as_a_rise():
    r = rc.recurring_costs([tpl(1, "Phone", 80)], [pay(1, "2026-08-01", 100), pay(1, "2026-09-01", 80)], TODAY)
    c = r["items"][0]["price_change"]
    assert c["direction"] == "down" and c["pct_change"] == -20.0 and r["price_rises"] == 0


def test_only_the_latest_change_is_reported():
    payments = [pay(1, "2026-05-01", 50), pay(1, "2026-06-01", 70), pay(1, "2026-07-01", 70), pay(1, "2026-08-01", 90)]
    c = rc.price_change(payments)
    assert (c["from"], c["to"], c["since"]) == (D("70.00"), D("90.00"), dt.date(2026, 8, 1))


def test_no_change_one_payment_or_none_means_no_price_change():
    assert rc.price_change([]) is None
    assert rc.price_change([pay(1, "2026-08-01", 100)]) is None
    assert rc.price_change([pay(1, "2026-08-01", 100), pay(1, "2026-09-01", 100)]) is None


def test_a_change_of_currency_is_not_a_price_rise():
    payments = [pay(1, "2026-08-01", 10, "EUR"), pay(1, "2026-09-01", 110, "SEK")]
    assert rc.price_change(payments) is None   # different currencies are never compared


def test_payments_on_the_same_day_are_ordered_by_id():
    payments = [pay(1, "2026-09-01", 120, id=2), pay(1, "2026-09-01", 100, id=1)]
    assert rc.price_change(payments)["to"] == D("120.00")


def test_a_template_in_another_currency_is_totalled_in_the_reporting_currency():
    r = rc.recurring_costs([tpl(1, "Spotify", 110, native=10, cur="EUR")], [], TODAY)
    i = r["items"][0]
    assert i["monthly"] == D("110.00") and i["native_amount"] == D("10.00") and i["native_currency"] == "EUR"
