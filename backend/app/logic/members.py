"""Spending by member in shared spaces: who paid for how much.

Only expenses filed in a shared space count (personal ones belong to nobody else's view). An
expense's `user_id` is who entered and paid it, the same person the trip settlement credits. Every
current member of the selected spaces is listed, spending nothing included, so a quiet member is
visible rather than missing. An expense with no owner (old data) is listed as one unnamed row.

Each member gets a total, share, count, average per expense and their top categories. On top of
that: a member-by-category table (the biggest few categories overall, the rest as "Other") and the
spending per month by member. Every expense counts, refunds included, so the total matches the other
reports. Categories that differ only in case or spacing are one.

Pure functions on plain dicts.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.names import clean_name, name_key
from app.logic.price_tracker import _as_day
from app.logic.report import UNCATEGORISED, _display_names

TOP_CATEGORIES = 6          # in the member-by-category table; the rest are "Other"
MEMBER_TOP_CATEGORIES = 3   # listed under each member
MAX_TREND_MONTHS = 24


def _share(part: Decimal, whole: Decimal) -> float:
    return round(float(part / whole * 100), 1) if whole else 0.0


def _month_range(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    end_y, end_m = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (end_y, end_m):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def spending_by_member(
    expenses: list[dict],
    members: list[dict],
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """`members`: [{"user_id", "name", "email"}, ...] of the selected spaces, any order."""
    rows: list[tuple[date, dict, Decimal]] = []
    for e in expenses:
        if e.get("group_id") is None:
            continue
        day = _as_day(e.get("date"))
        if day is None or (date_from and day < date_from) or (date_to and day > date_to):
            continue
        rows.append((day, e, as_decimal(e.get("amount"))))
    total = sum((a for _, _, a in rows), Decimal(0))

    known = {m["user_id"]: m for m in members}
    # Someone who has since left a space keeps no expenses there (they return to personal), but be
    # safe with an owner we were not told about: they get a row of their own rather than vanishing.
    extra = sorted({e.get("user_id") for _, e, _ in rows if e.get("user_id") is not None and e.get("user_id") not in known})
    owners = list(known) + extra + ([None] if any(e.get("user_id") is None for _, e, _ in rows) else [])

    category_names = _display_names([e.get("category") or UNCATEGORISED for _, e, _ in rows])
    per_owner_total: dict = defaultdict(lambda: Decimal(0))
    per_owner_count: dict = defaultdict(int)
    per_owner_cat: dict = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    category_total: dict = defaultdict(lambda: Decimal(0))
    month_owner: dict = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    for day, e, amount in rows:
        owner = e.get("user_id")
        key = name_key(e.get("category") or UNCATEGORISED)
        per_owner_total[owner] += amount
        per_owner_count[owner] += 1
        per_owner_cat[owner][key] += amount
        category_total[key] += amount
        month_owner[f"{day.year:04d}-{day.month:02d}"][owner] += amount

    def label(owner) -> dict:
        m = known.get(owner)
        if m:
            return {"user_id": owner, "name": clean_name(m.get("name")), "email": m.get("email") or ""}
        return {"user_id": owner, "name": "" if owner is None else "Former member", "email": ""}

    out_members = []
    for owner in owners:
        count = per_owner_count[owner]
        t = per_owner_total[owner]
        top = sorted(per_owner_cat[owner].items(), key=lambda kv: (-kv[1], category_names[kv[0]]))[:MEMBER_TOP_CATEGORIES]
        out_members.append({
            **label(owner),
            "total": quantize_money(t),
            "count": count,
            "share_pct": _share(t, total),
            "avg_per_expense": quantize_money(t / count) if count else quantize_money(0),
            "top_categories": [{"category": category_names[k], "total": quantize_money(v)} for k, v in top],
        })
    out_members.sort(key=lambda m: (-m["total"], (m["name"] or m["email"]).lower(), m["user_id"] or 0))

    ranked = sorted(category_total.items(), key=lambda kv: (-kv[1], category_names[kv[0]]))
    shown, rest = ranked[:TOP_CATEGORIES], ranked[TOP_CATEGORIES:]
    categories = [
        {
            "category": category_names[k],
            "total": quantize_money(v),
            "by_member": [{"user_id": o, "total": quantize_money(per_owner_cat[o][k])} for o in owners],
        }
        for k, v in shown
    ]
    if rest:
        categories.append({
            "category": "Other",
            "other": True,
            "count": len(rest),
            "total": quantize_money(sum((v for _, v in rest), Decimal(0))),
            "by_member": [{"user_id": o, "total": quantize_money(sum((per_owner_cat[o][k] for k, _ in rest), Decimal(0)))} for o in owners],
        })

    months: list[dict] = []
    if month_owner:
        every = _month_range(min(month_owner), max(month_owner))
        for month in every[-MAX_TREND_MONTHS:]:
            months.append({
                "month": month,
                "total": quantize_money(sum(month_owner[month].values(), Decimal(0))),
                "by_member": [{"user_id": o, "total": quantize_money(month_owner[month][o])} for o in owners],
            })

    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "member_count": len(known),
        "total": quantize_money(total),
        "count": len(rows),
        "members": out_members,
        "categories": categories,
        "months": months,
        "months_total": len(_month_range(min(month_owner), max(month_owner))) if month_owner else 0,
    }
