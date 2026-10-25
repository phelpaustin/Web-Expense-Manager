"""Budget alerts now use the chance of exceeding a budget where there is history, and the old pace rule where not."""
from decimal import Decimal as D

import pytest

from app.api.alerts import _digest_signature
from app.logic import alerts as al
from app.logic import budget_risk as br


def risk_item(category="Total", probability=80.0, level=None, available=True, exceeded=7, samples=9, align="month",
              remaining=500, is_total=None, reason=None):
    return {
        "category": category, "is_total": (category == "Total") if is_total is None else is_total, "available": available,
        "probability": probability if available else None, "level": (level or br.level_for(probability)) if available else None,
        "exceeded": exceeded, "samples": samples, "align": align, "remaining": D(remaining), "reason": reason,
    }


def risk(*items):
    return {"items": list(items)}


def period(effective=11000, spent=10200, projected=15000, kind="Monthly"):
    return {"period": kind, "label": "October 2026", "budget": D(effective), "rollover": D(0), "effective": D(effective),
            "spent": D(spent), "remaining": D(effective - spent), "pct": round(spent / effective * 100, 1), "projected": D(projected),
            "days_total": 31, "days_elapsed": 21, "days_remaining": 10, "status": "ok"}


def category(name="Groceries", budget=1000, spent=600):
    return {"category": name, "budget": D(budget), "spent": D(spent), "remaining": D(budget - spent),
            "pct": round(spent / budget * 100, 1), "status": "ok"}


def ids(alerts):
    return [a["id"] for a in alerts]


# --- without risk, nothing changes -------------------------------------------------------------

def test_without_any_risk_the_straight_line_alert_is_unchanged():
    [a] = al.generate_alerts([], period(projected=15000))

    assert a["id"] == "predictive:period" and a["message"].startswith("On pace to spend 15000.00 this month")


def test_without_risk_there_are_no_risk_alerts():
    assert all(not i.startswith("risk:") for i in ids(al.generate_alerts([category(spent=700)], None)))


# --- the total budget --------------------------------------------------------------------------

def test_a_high_chance_of_exceeding_the_total_budget_warns_with_the_evidence():
    [a] = al.generate_alerts([], period(), risk(risk_item("Total", probability=81.4, exceeded=7, samples=9, remaining=800)))

    assert a["id"] == "predictive:period" and a["severity"] == "warning" and a["category"] == "Total"
    assert a["message"] == ("About 81% chance of going over your 11000.00 budget this month: in 7 of the last 9 months, "
                            "the remaining days' spending went past what you have left")


def test_a_low_chance_silences_the_straight_line_alert_it_would_have_raised():
    # The old rule projects 15,000 against 11,000 (rent on day 1) and warns; the history says 5%.
    alerts = al.generate_alerts([], period(projected=15000), risk(risk_item("Total", probability=5.0)))

    assert alerts == []


def test_the_threshold_is_inclusive_at_75_percent():
    assert ids(al.generate_alerts([], period(), risk(risk_item("Total", probability=75.0)))) == ["predictive:period"]
    assert al.generate_alerts([], period(), risk(risk_item("Total", probability=74.9))) == []


def test_too_little_history_falls_back_to_the_straight_line_rule():
    unavailable = risk_item("Total", available=False, reason="not_enough_history")

    [a] = al.generate_alerts([], period(projected=15000), risk(unavailable))

    assert a["message"].startswith("On pace to spend")


def test_when_there_is_no_total_item_in_the_risk_the_old_rule_still_applies():
    [a] = al.generate_alerts([], period(projected=15000), risk(risk_item("Groceries", probability=10)))

    assert a["message"].startswith("On pace to spend")


def test_already_over_is_left_to_the_exceeded_alert_not_a_prediction():
    over = risk_item("Total", probability=100.0, level="over")

    assert al.generate_alerts([], period(spent=12000, projected=15000), risk(over)) == []


def test_a_weekly_budget_talks_about_weeks():
    [a] = al.generate_alerts([], period(kind="Weekly"), risk(risk_item("Total", probability=90, align="week", exceeded=10, samples=12)))

    assert "this week" in a["message"] and "10 of the last 12 weeks" in a["message"]


# --- category budgets --------------------------------------------------------------------------

def test_a_category_likely_to_go_over_gets_its_own_alert():
    item = risk_item("Groceries", probability=80.0, exceeded=6, samples=8, remaining=400)

    alerts = al.generate_alerts([category("Groceries", 1000, 600)], None, risk(item))

    [a] = [a for a in alerts if a["id"] == "risk:Groceries"]
    assert a["severity"] == "warning" and a["category"] == "Groceries"
    assert a["message"] == ("Groceries budget: about 80% chance of going over this month (400.00 left; in 6 of the last 8 months, "
                            "the remaining days' spending went past what you have left)")


def test_category_alerts_need_the_threshold_history_and_a_budget_not_yet_exceeded():
    below = risk_item("Groceries", probability=74.0)
    unavailable = risk_item("Dining", available=False, reason="not_enough_history")
    over = risk_item("Fun", probability=100.0, level="over")

    alerts = al.generate_alerts([category("Groceries"), category("Dining"), category("Fun", 100, 150)], None, risk(below, unavailable, over))

    assert not any(i.startswith("risk:") for i in ids(alerts))


def test_the_total_is_never_a_category_risk_alert():
    alerts = al.generate_alerts([], None, risk(risk_item("Total", probability=95)))

    assert not any(i.startswith("risk:") for i in ids(alerts))


def test_alerts_stay_sorted_with_the_most_serious_first():
    exceeded = category("Rent", 100, 150)
    exceeded["status"] = "exceeded"
    alerts = al.generate_alerts([exceeded], period(), risk(risk_item("Total", probability=90), risk_item("Groceries", probability=88)))

    ranks = [al.SEVERITY_RANK[a["severity"]] for a in alerts]
    assert ranks == sorted(ranks, reverse=True) and alerts[0]["severity"] == "critical"


# --- the daily digest stays quiet --------------------------------------------------------------

def test_the_digest_fingerprint_ignores_changing_percentages_and_amounts():
    day1 = al.generate_alerts([], period(), risk(risk_item("Total", probability=78.0, remaining=500)))
    day2 = al.generate_alerts([], period(), risk(risk_item("Total", probability=92.0, remaining=120)))

    assert day1[0]["message"] != day2[0]["message"]
    assert _digest_signature(day1) == _digest_signature(day2)


def test_the_digest_fingerprint_changes_only_when_an_alert_appears_or_goes():
    quiet = al.generate_alerts([], period(), risk(risk_item("Total", probability=10)))
    warned = al.generate_alerts([], period(), risk(risk_item("Total", probability=90)))

    assert _digest_signature(quiet) != _digest_signature(warned)
