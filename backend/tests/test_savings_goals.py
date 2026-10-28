"""Savings goal progress and pace."""
import datetime as dt
import math
from decimal import Decimal as D

from app.logic import savings_goals as sg

TODAY = dt.date(2026, 10, 28)


def goal(target=1000, when=None, **extra):
    return {"id": 1, "name": "Trip", "target_amount": D(str(target)), "target_date": dt.date.fromisoformat(when) if when else None, **extra}


def put(date, amount):
    return {"date": dt.date.fromisoformat(date), "amount": D(str(amount))}


def prog(g, rows=(), today=TODAY):
    return sg.goal_progress(g, list(rows), today)


def test_nothing_saved_yet():
    p = prog(goal(1000))
    assert (p["saved"], p["remaining"], p["pct"], p["reached"], p["status"]) == (D("0.00"), D("1000.00"), 0.0, False, "no_deadline")
    assert p["contribution_count"] == 0 and p["last_contribution"] is None and p["projected_date"] is None and p["recent_per_month"] == D("0.00")


def test_saved_is_the_sum_of_deposits_and_withdrawals():
    p = prog(goal(1000), [put("2026-09-01", 400), put("2026-09-20", 250), put("2026-10-01", -100)])
    assert p["saved"] == D("550.00") and p["remaining"] == D("450.00") and p["pct"] == 55.0 and p["contribution_count"] == 3
    assert p["last_contribution"] == "2026-10-01"


def test_a_contribution_dated_tomorrow_counts_too():
    """Someone just ahead of the server's clock (Stockholm just after midnight) enters tomorrow's date."""
    p = prog(goal(1000), [put("2026-10-29", 100)])
    assert p["saved"] == D("100.00") and p["last_contribution"] == "2026-10-29" and p["recent_per_month"] == D("100.00")
    assert sg.saved_total([put("2026-10-29", 100), {"date": "bad", "amount": 5}]) == 100


def test_reaching_the_target_ends_the_chase():
    p = prog(goal(1000, "2027-06-01"), [put("2026-09-01", 1000)])
    assert (p["reached"], p["status"], p["remaining"], p["pct"]) == (True, "reached", D("0.00"), 100.0)
    assert p["needed_per_month"] is None and p["projected_date"] is None and p["shortfall_per_month"] is None
    over = prog(goal(1000), [put("2026-09-01", 1500)])
    assert over["reached"] and over["remaining"] == D("0.00") and over["pct"] == 150.0


def test_the_amount_needed_per_month_to_make_the_date():
    p = prog(goal(1000, "2027-04-28"), [put("2026-10-01", 400)])      # 182 days left = 5.98 months
    assert p["days_left"] == 182 and p["needed_per_month"] == (D(600) / (D(182) / D("30.4375"))).quantize(D("0.01"))


def test_the_need_is_never_spread_over_less_than_a_month():
    p = prog(goal(1000, "2026-11-03"), [put("2026-10-01", 400)])      # 6 days left
    assert p["needed_per_month"] == D("600.00")


def test_no_need_without_a_future_date():
    assert prog(goal(1000), [put("2026-10-01", 1)])["needed_per_month"] is None
    assert prog(goal(1000, "2026-10-28"), [put("2026-10-01", 1)])["needed_per_month"] is None   # due today: nothing left to spread


def test_the_recent_pace_looks_back_90_days():
    rows = [put("2026-05-01", 5000), put("2026-08-01", 300), put("2026-09-01", 300), put("2026-10-01", 300)]   # the May deposit is too old
    p = prog(goal(100000), rows)
    assert p["recent_per_month"] == (D(900) / (D(90) / D("30.4375"))).quantize(D("0.01"))


def test_a_first_deposit_is_not_mistaken_for_a_months_saving_but_not_diluted_either():
    p = prog(goal(10000), [put("2026-10-27", 600)])                    # 2 days of history counts as one month
    assert p["recent_per_month"] == D("600.00")
    p = prog(goal(10000), [put("2026-09-28", 600)])                    # 31 days = 1.02 months
    assert p["recent_per_month"] == (D(600) / (D(31) / D("30.4375"))).quantize(D("0.01"))


def test_withdrawals_slow_the_pace_and_a_negative_pace_counts_as_none():
    assert prog(goal(10000), [put("2026-09-01", 900), put("2026-10-01", -300)])["recent_per_month"] > 0
    p = prog(goal(10000), [put("2026-05-01", 900), put("2026-10-01", -300)])
    assert p["recent_per_month"] == D("0.00") and p["projected_date"] is None


def test_the_projected_date_is_when_the_pace_reaches_the_target():
    p = prog(goal(1000), [put("2026-09-28", 300), put("2026-10-28", 300)])        # 600 saved, ~295/month
    pace = D(600) / (D(31) / D("30.4375"))
    days = math.ceil(D(400) / pace * D("30.4375"))
    assert p["projected_date"] == (TODAY + dt.timedelta(days=days)).isoformat() == "2026-11-18"


def test_on_track_when_the_pace_makes_the_date_and_behind_when_it_does_not():
    rows = [put("2026-09-28", 300), put("2026-10-28", 300)]
    assert prog(goal(1000, "2027-12-31"), rows)["status"] == "on_track"
    assert prog(goal(1000, "2026-11-18"), rows)["status"] == "on_track"            # exactly on the day counts
    assert prog(goal(1000, "2026-11-17"), rows)["status"] == "behind"              # a day short does not
    behind = prog(goal(3000, "2026-12-15"), rows)
    assert behind["status"] == "behind" and behind["shortfall_per_month"] > 0
    assert behind["shortfall_per_month"] == (behind["needed_per_month"] - behind["recent_per_month"]).quantize(D("0.01"))


def test_a_date_with_no_pace_at_all_is_behind():
    p = prog(goal(1000, "2027-12-31"), [put("2026-01-01", 100)])      # nothing in the last 90 days
    assert p["status"] == "behind" and p["projected_date"] is None and p["shortfall_per_month"] == p["needed_per_month"]


def test_overdue_when_the_date_passed_without_reaching_it():
    p = prog(goal(1000, "2026-10-01"), [put("2026-09-01", 400)])
    assert p["status"] == "overdue" and p["days_left"] == -27 and p["needed_per_month"] is None
    assert prog(goal(1000, "2026-10-01"), [put("2026-09-01", 1000)])["status"] == "reached"


def test_a_goal_with_no_date_still_gets_a_projection_when_there_is_a_pace():
    p = prog(goal(1000), [put("2026-09-28", 300), put("2026-10-28", 300)])
    assert p["status"] == "no_deadline" and p["projected_date"] is not None and p["days_left"] is None


def test_a_hopelessly_slow_pace_has_no_projection():
    p = prog(goal(10_000_000), [put("2026-10-27", 1)])
    assert p["projected_date"] is None


def test_strings_work_for_dates_and_amounts():
    p = sg.goal_progress({"target_amount": "500", "target_date": "2027-01-01"}, [{"date": "2026-10-01", "amount": "100.50"}], TODAY)
    assert p["saved"] == D("100.50") and p["days_left"] == 65


def test_a_zero_target_does_not_divide_by_zero():
    p = prog(goal(0), [put("2026-10-01", 5)])
    assert p["pct"] == 0.0 and p["reached"] is False


def test_goals_sort_unfinished_first_by_date_then_undated_then_reached():
    goals = [
        {"id": 1, "name": "Done", "status": "reached", "target_date": "2026-01-01"},
        {"id": 2, "name": "Someday", "status": "no_deadline", "target_date": None},
        {"id": 3, "name": "Later", "status": "on_track", "target_date": "2027-06-01"},
        {"id": 4, "name": "Soon", "status": "behind", "target_date": "2026-12-01"},
        {"id": 5, "name": "alpha", "status": "no_deadline", "target_date": None},
    ]
    assert [g["name"] for g in sg.sort_goals(goals)] == ["Soon", "Later", "alpha", "Someday", "Done"]


def test_the_summary_counts_goals_reached_and_behind():
    goals = [{"status": s} for s in ("reached", "reached", "behind", "overdue", "on_track", "no_deadline")]
    assert sg.summary(goals) == {"goals": 6, "reached": 2, "behind": 2}
    assert sg.summary([]) == {"goals": 0, "reached": 0, "behind": 0}


def test_sorting_works_with_real_dates_as_the_api_passes_them():
    goals = [
        {"id": 1, "name": "Undated", "status": "no_deadline", "target_date": None},
        {"id": 2, "name": "Dated", "status": "on_track", "target_date": dt.date(2027, 1, 1)},
        {"id": 3, "name": "Sooner", "status": "behind", "target_date": dt.date(2026, 12, 1)},
        {"id": 4, "name": "Text date", "status": "behind", "target_date": "2026-11-01"},
    ]
    assert [g["name"] for g in sg.sort_goals(goals)] == ["Text date", "Sooner", "Dated", "Undated"]
