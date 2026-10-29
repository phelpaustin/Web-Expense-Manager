"""Spending by member in shared spaces."""
import datetime as dt
from decimal import Decimal as D

from app.logic import members as mb

_ids = iter(range(1, 100_000))
ANN = {"user_id": 1, "name": "Ann", "email": "ann@example.com"}
BOB = {"user_id": 2, "name": "Bob", "email": "bob@example.com"}
CAT = {"user_id": 3, "name": "", "email": "cat@example.com"}


def e(user, date, amount, category="Food", group=10):
    return {"id": next(_ids), "user_id": user, "group_id": group, "date": dt.date.fromisoformat(date), "amount": D(str(amount)), "category": category}


def run(rows, members=(ANN, BOB), **kw):
    return mb.spending_by_member(rows, list(members), **kw)


def by_id(result):
    return {m["user_id"]: m for m in result["members"]}


def test_each_member_gets_a_total_share_count_and_average():
    r = run([e(1, "2026-10-01", 300), e(1, "2026-10-02", 100), e(2, "2026-10-03", 100)])
    ann, bob = by_id(r)[1], by_id(r)[2]
    assert (ann["total"], ann["count"], ann["share_pct"], ann["avg_per_expense"]) == (D("400.00"), 2, 80.0, D("200.00"))
    assert (bob["total"], bob["count"], bob["share_pct"], bob["avg_per_expense"]) == (D("100.00"), 1, 20.0, D("100.00"))
    assert (r["total"], r["count"], r["member_count"]) == (D("500.00"), 3, 2)
    assert [m["name"] for m in r["members"]] == ["Ann", "Bob"]                         # biggest spender first


def test_a_member_who_has_spent_nothing_is_still_listed():
    r = run([e(1, "2026-10-01", 50)], members=(ANN, BOB, CAT))
    assert [(m["user_id"], m["total"], m["count"], m["share_pct"]) for m in r["members"]] == [
        (1, D("50.00"), 1, 100.0), (2, D("0.00"), 0, 0.0), (3, D("0.00"), 0, 0.0)]
    assert by_id(r)[2]["avg_per_expense"] == D("0.00") and by_id(r)[2]["top_categories"] == []


def test_ties_are_ordered_by_name_and_a_member_without_a_name_uses_the_email():
    r = run([e(2, "2026-10-01", 10), e(1, "2026-10-01", 10), e(3, "2026-10-01", 10)], members=(BOB, CAT, ANN))
    assert [m["user_id"] for m in r["members"]] == [1, 2, 3]                            # Ann, Bob, then cat@example.com
    assert by_id(r)[3]["name"] == "" and by_id(r)[3]["email"] == "cat@example.com"


def test_only_expenses_in_a_shared_space_count():
    r = run([e(1, "2026-10-01", 100), e(1, "2026-10-01", 900, group=None)])
    assert r["total"] == D("100.00") and r["count"] == 1


def test_the_period_is_inclusive_at_both_ends():
    rows = [e(1, "2026-09-30", 1), e(1, "2026-10-01", 10), e(1, "2026-10-31", 100), e(1, "2026-11-01", 1000)]
    r = run(rows, date_from=dt.date(2026, 10, 1), date_to=dt.date(2026, 10, 31))
    assert r["total"] == D("110.00") and (r["date_from"], r["date_to"]) == ("2026-10-01", "2026-10-31")
    assert run(rows)["total"] == D("1111.00") and run(rows)["date_from"] is None
    assert run(rows, date_from=dt.date(2026, 10, 31))["total"] == D("1100.00")
    assert run(rows, date_to=dt.date(2026, 9, 30))["total"] == D("1.00")


def test_top_categories_per_member_biggest_first_and_capped_at_three():
    rows = [e(1, "2026-10-01", 10, "Food"), e(1, "2026-10-02", 50, "Rent"), e(1, "2026-10-03", 30, "Fun"), e(1, "2026-10-04", 20, "Travel"), e(1, "2026-10-05", 5, "food")]
    top = by_id(run(rows))[1]["top_categories"]
    assert [(c["category"], c["total"]) for c in top] == [("Rent", D("50.00")), ("Fun", D("30.00")), ("Travel", D("20.00"))]
    assert by_id(run(rows))[1]["top_categories"][0]["category"] == "Rent"


def test_categories_that_differ_only_in_case_are_one():
    r = run([e(1, "2026-10-01", 10, "food"), e(2, "2026-10-01", 10, "Food "), e(1, "2026-10-02", 10, "FOOD")])
    assert [(c["category"], c["total"]) for c in r["categories"]] == [("FOOD", D("30.00"))]     # a tie in spellings goes to the first alphabetically
    assert [(c["category"], c["total"]) for c in run([e(1, "2026-10-01", 5, "Food"), e(1, "2026-10-02", 5, "Food"), e(1, "2026-10-03", 5, "food")])["categories"]] == [("Food", D("15.00"))]


def test_the_category_table_shows_each_members_part_and_groups_the_tail():
    rows = [e(1, "2026-10-01", 100 + i, f"C{i}") for i in range(8)] + [e(2, "2026-10-02", 7, "C0"), e(2, "2026-10-02", 3, "C7")]
    r = run(rows)                                      # C7 110, C0 107, C6 106, C5 105, C4 104, C3 103, then C2 102 and C1 101
    assert [c["category"] for c in r["categories"]] == ["C7", "C0", "C6", "C5", "C4", "C3", "Other"]
    c0 = r["categories"][1]
    assert c0["total"] == D("107.00") and {b["user_id"]: b["total"] for b in c0["by_member"]} == {1: D("100.00"), 2: D("7.00")}
    other = r["categories"][-1]
    assert other["other"] is True and other["count"] == 2 and other["total"] == D("203.00")
    assert {b["user_id"]: b["total"] for b in other["by_member"]} == {1: D("203.00"), 2: D("0.00")}
    assert "other" not in c0


def test_other_and_the_listed_categories_add_up_to_the_total():
    rows = [e(1 + i % 2, f"2026-10-{1 + i % 27:02d}", 10 + i, f"C{i % 9}") for i in range(40)]
    r = run(rows)
    assert sum(c["total"] for c in r["categories"]) == r["total"] == sum(m["total"] for m in r["members"])
    for c in r["categories"]:
        assert sum(b["total"] for b in c["by_member"]) == c["total"]


def test_the_monthly_trend_is_contiguous_and_split_by_member():
    rows = [e(1, "2026-08-15", 100), e(2, "2026-08-20", 50), e(1, "2026-10-02", 70)]
    r = run(rows)
    assert [m["month"] for m in r["months"]] == ["2026-08", "2026-09", "2026-10"]          # September is there, empty
    aug, sep, octo = r["months"]
    assert aug["total"] == D("150.00") and {b["user_id"]: b["total"] for b in aug["by_member"]} == {1: D("100.00"), 2: D("50.00")}
    assert sep["total"] == D("0.00") and all(b["total"] == 0 for b in sep["by_member"])
    assert octo["total"] == D("70.00") and r["months_total"] == 3


def test_the_trend_spans_a_year_boundary_and_keeps_only_the_latest_24_months():
    r = run([e(1, "2025-11-05", 1), e(1, "2026-02-05", 1)])
    assert [m["month"] for m in r["months"]] == ["2025-11", "2025-12", "2026-01", "2026-02"]
    long = run([e(1, "2023-01-05", 1), e(1, "2026-10-05", 1)])
    assert len(long["months"]) == 24 and long["months"][-1]["month"] == "2026-10" and long["months"][0]["month"] == "2024-11" and long["months_total"] == 46


def test_no_expenses_gives_empty_lists_but_still_lists_members():
    r = run([])
    assert r["total"] == D("0.00") and r["count"] == 0 and r["categories"] == [] and r["months"] == [] and r["months_total"] == 0
    assert [m["total"] for m in r["members"]] == [D("0.00"), D("0.00")]


def test_refunds_count_so_totals_match_the_other_reports():
    r = run([e(1, "2026-10-01", 100), e(1, "2026-10-02", -30)])
    assert by_id(r)[1]["total"] == D("70.00") and r["total"] == D("70.00")


def test_an_expense_with_no_owner_gets_an_unnamed_row():
    r = run([e(1, "2026-10-01", 10), e(None, "2026-10-02", 90)])
    nobody = next(m for m in r["members"] if m["user_id"] is None)
    assert nobody["name"] == "" and nobody["total"] == D("90.00") and nobody["share_pct"] == 90.0
    assert [m["user_id"] for m in r["members"]][0] is None                              # the biggest, so first


def test_an_owner_who_is_not_a_listed_member_is_shown_as_a_former_member():
    r = run([e(9, "2026-10-01", 40)])
    former = next(m for m in r["members"] if m["user_id"] == 9)
    assert former["name"] == "Former member" and former["total"] == D("40.00")


def test_the_share_of_a_zero_total_is_zero_not_an_error():
    r = run([e(1, "2026-10-01", 10), e(2, "2026-10-01", -10)])
    assert r["total"] == D("0.00") and all(m["share_pct"] == 0.0 for m in r["members"])


def test_rows_with_a_bad_date_are_ignored_and_dates_may_be_text():
    rows = [{"user_id": 1, "group_id": 10, "date": "nope", "amount": 5, "category": "Food"}, {"user_id": 1, "group_id": 10, "date": "2026-10-01", "amount": "7.5", "category": "Food"}]
    r = run(rows)
    assert r["total"] == D("7.50") and r["count"] == 1


def test_an_uncategorised_expense_has_a_category_of_its_own():
    r = run([e(1, "2026-10-01", 10, ""), e(1, "2026-10-02", 5, None)])
    assert [(c["category"], c["total"]) for c in r["categories"]] == [("Uncategorised", D("15.00"))]
