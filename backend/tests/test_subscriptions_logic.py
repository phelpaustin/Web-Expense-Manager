"""The subscription detector: what counts as a subscription and what does not."""
from datetime import date, timedelta
from decimal import Decimal

from app.logic.subscriptions import find_subscriptions

D = Decimal
TODAY = date(2026, 11, 10)


def _p(day, amount, shop="Spotify", currency="SEK", **kw):
    return {"id": kw.pop("id", None), "date": day, "amount": D(str(amount)), "currency": currency, "shop": shop,
            "description": kw.pop("description", ""), "category": kw.pop("category", "Entertainment"), **kw}


def _monthly(shop="Spotify", amounts=(119,) * 6, start=date(2026, 5, 3), **kw):
    out, d = [], start
    for a in amounts:
        out.append(_p(d, a, shop, **kw))
        m = d.month % 12 + 1
        d = d.replace(year=d.year + (d.month == 12), month=m)
    return out


def _find(purchases, **kw):
    return find_subscriptions(purchases, today=TODAY, **kw)


def test_a_steady_monthly_charge_is_a_subscription_with_its_cost():
    [s] = _find(_monthly())["items"]
    assert (s["name"], s["frequency"], s["charges"], s["varies"]) == ("Spotify", "Monthly", 6, False)
    assert s["amount"] == D("119.00") and s["monthly_native"] == D("119.00") and s["yearly_native"] == D("1428.00")
    assert s["last_date"] == date(2026, 10, 3) and s["next_due"] == date(2026, 11, 3)
    assert s["currency"] == "SEK" and s["category"] == "Entertainment" and s["price_change"] is None


def test_other_rhythms_are_recognised_and_costed_per_month():
    weekly = [_p(date(2026, 9, 12) + timedelta(days=7 * i), 50, "Pool") for i in range(8)]
    biweekly = [_p(date(2026, 9, 5) + timedelta(days=14 * i), 100, "Cleaner") for i in range(5)]
    yearly = [_p(date(2024, 11, 20), 899, "Antivirus"), _p(date(2025, 11, 20), 899, "Antivirus")]
    quarterly = [_p(date(2026, 1, 25), 300, "Insurance"), _p(date(2026, 4, 25), 300, "Insurance"), _p(date(2026, 7, 25), 300, "Insurance")]
    by = {s["name"]: s for s in _find(weekly + biweekly + yearly + quarterly)["items"]}
    assert {k: v["frequency"] for k, v in by.items()} == {"Pool": "Weekly", "Cleaner": "Bi-weekly", "Antivirus": "Yearly", "Insurance": "Quarterly"}
    assert by["Pool"]["monthly_native"] == D("216.67") and by["Cleaner"]["monthly_native"] == D("216.67")
    assert by["Antivirus"]["monthly_native"] == D("74.92") and by["Insurance"]["monthly_native"] == D("100.00")


def test_too_few_charges_do_not_count():
    assert _find(_monthly(amounts=(119, 119)))["items"] == []                       # two months
    assert _find([_p(date(2026, 1, 1), 50, "Pool") for _ in range(1)])["items"] == []  # one charge
    weekly4 = [_p(date(2026, 9, 12) + timedelta(days=7 * i), 50, "Pool") for i in range(4)]
    assert _find(weekly4)["items"] == []                                           # weekly needs five


def test_irregular_purchases_at_the_same_shop_are_not_subscriptions():
    days = [date(2026, 1, 3), date(2026, 1, 20), date(2026, 3, 9), date(2026, 3, 11), date(2026, 6, 30)]
    assert _find([_p(d, 119, "Lidl") for d in days])["items"] == []


def test_amounts_that_swing_widely_are_not_subscriptions_but_small_swings_are_flagged_as_varying():
    assert _find(_monthly("Shop", amounts=(100, 300, 90, 400, 150, 80)))["items"] == []
    [phone] = _find(_monthly("Telia", amounts=(300, 400, 340, 450, 360, 330)))["items"]
    assert phone["varies"] is True and phone["price_change"] is None


def test_a_price_rise_is_reported_for_fixed_prices():
    [s] = _find(_monthly("Netflix", amounts=(109, 109, 109, 109, 129, 129)))["items"]
    assert s["varies"] is False and s["amount"] == D("129.00")
    pc = s["price_change"]
    assert (pc["from"], pc["to"], pc["direction"], pc["pct_change"]) == (D("109.00"), D("129.00"), "up", 18.3)


def test_one_charge_per_day_and_refunds_are_ignored():
    rows = _monthly()
    rows.append(_p(rows[1]["date"], 119))               # the same charge twice on one day
    rows.append(_p(date(2026, 6, 20), -119, "Spotify"))  # a refund
    [s] = _find(rows)["items"]
    assert s["charges"] == 6 and s["amount"] == D("119.00")


def test_names_match_without_regard_to_case_and_spacing_and_currencies_stay_apart():
    rows = [_p(r["date"], 119, "SPOTIFY  ") if i % 2 else r for i, r in enumerate(_monthly())]
    [s] = _find(rows)["items"]
    assert s["charges"] == 6
    eur = _monthly("Spotify", currency="EUR")
    items = _find(_monthly() + eur)["items"]
    assert sorted(i["currency"] for i in items) == ["EUR", "SEK"]


def test_without_a_shop_the_description_is_the_name():
    rows = [_p(r["date"], 99, "", description="Gym membership") for r in _monthly()]
    [s] = _find(rows)["items"]
    assert s["name"] == "Gym membership"


def test_a_subscription_that_stopped_is_listed_apart():
    old = _monthly("Old gym", amounts=(250,) * 4, start=date(2026, 2, 1))   # last charge 2026-05-01
    out = _find(old + _monthly())
    assert [s["name"] for s in out["items"]] == ["Spotify"]
    assert [s["name"] for s in out["stopped"]] == ["Old gym"]


def test_a_charge_a_few_days_late_is_not_stopped_and_one_long_gone_is_dropped():
    late = _monthly("Spotify", start=date(2026, 5, 7))                 # next expected 2026-11-07, today 11-10
    assert [s["name"] for s in _find(late)["items"]] == ["Spotify"]
    ancient = _monthly("Ancient", amounts=(50,) * 4, start=date(2024, 1, 1))
    assert _find(ancient) == {"items": [], "stopped": [], "tracked_count": 0}


def test_tracked_ignored_and_template_posted_ones_are_left_out():
    base = _monthly()
    assert _find(base, tracked_keys={"spotify"}) == {"items": [], "stopped": [], "tracked_count": 1}
    assert _find(base, ignored_keys={"spotify"}) == {"items": [], "stopped": [], "tracked_count": 0}
    posted = [{**r, "tracked": True} if i == 5 else r for i, r in enumerate(base)]
    assert _find(posted)["tracked_count"] == 1 and _find(posted)["items"] == []


def test_items_are_sorted_by_monthly_cost():
    out = _find(_monthly("Small", amounts=(49,) * 4, start=date(2026, 7, 3)) + _monthly("Big", amounts=(899,) * 4, start=date(2026, 7, 3)) + _monthly("Mid", amounts=(299,) * 4, start=date(2026, 7, 3)))
    assert [s["name"] for s in out["items"]] == ["Big", "Mid", "Small"]
