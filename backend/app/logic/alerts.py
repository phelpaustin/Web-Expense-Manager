"""Budget alert generation — a thin layer over budgets_logic's status calculations.

No persistence: alerts are recomputed from current budget/spending state on
every request, so there's nothing to keep in sync or clean up.
"""
from __future__ import annotations

from app.logic.budget_risk import ALERT_THRESHOLD

SEVERITY_RANK = {"critical": 3, "warning": 2, "caution": 1, "info": 0}


def _category_alert(status: dict) -> dict | None:
    pct = status["pct"]
    category = status["category"]
    label = "Overall budget" if category == "Total" else f"{category} budget"

    if status["status"] == "exceeded":
        severity = "critical"
        message = (
            f"{label} exceeded: {status['spent']:.2f} spent of {status['budget']:.2f} "
            f"({pct:.0f}%, {abs(status['remaining']):.2f} over)"
        )
    elif status["status"] == "warning":
        severity = "warning"
        message = f"{label} is at {pct:.0f}% — {status['remaining']:.2f} remaining"
    elif status["status"] == "caution":
        severity = "caution"
        message = f"{label} is at {pct:.0f}% of {status['budget']:.2f}"
    else:
        return None

    return {
        "id": f"category:{category}",
        "severity": severity,
        "category": category,
        "message": message,
    }


def _period_label(period: str) -> str:
    return {"Weekly": "this week", "Monthly": "this month", "Annual": "by the end of this month"}.get(period, "this period")


def _evidence(item: dict) -> str:
    """Why the chance is what it is: how often the same stretch of past periods went past the room left."""
    unit = "weeks" if item["align"] == "week" else "months"
    return f"in {item['exceeded']} of the last {item['samples']} {unit}, the remaining days' spending went past what you have left"


def _likely_to_exceed(item: dict | None) -> bool:
    return bool(item and item["available"] and item["level"] != "over" and item["probability"] >= ALERT_THRESHOLD)


def _predictive_alert(period_status: dict | None, risk_item: dict | None = None) -> dict | None:
    """Warn when the period's budget is likely to be exceeded, even if it is not yet.

    With enough history this is the chance worked out from earlier periods (see budget_risk), which
    does not mistake a big bill on day 1 for a pace. With too little history it falls back to the
    straight-line pace, as before.
    """
    if not period_status:
        return None
    effective = period_status["effective"]
    if risk_item is not None and risk_item["available"]:
        if not _likely_to_exceed(risk_item):
            return None
        return {
            "id": "predictive:period",
            "severity": "warning",
            "category": "Total",
            "message": (
                f"About {risk_item['probability']:.0f}% chance of going over your {effective:.2f} budget "
                f"{_period_label(period_status['period'])}: {_evidence(risk_item)}"
            ),
        }
    projected = period_status["projected"]
    if effective <= 0 or projected <= effective or period_status["pct"] >= 100:
        return None
    over_by = projected - effective
    return {
        "id": "predictive:period",
        "severity": "warning",
        "category": "Total",
        "message": (
            f"On pace to spend {projected:.2f} {_period_label(period_status['period'])} "
            f"— {over_by:.2f} over your {effective:.2f} budget"
        ),
    }


def _category_risk_alert(item: dict) -> dict | None:
    """A category budget that is likely to be exceeded by month end (and is not yet)."""
    if item["is_total"] or not _likely_to_exceed(item):
        return None
    return {
        "id": f"risk:{item['category']}",
        "severity": "warning",
        "category": item["category"],
        "message": (
            f"{item['category']} budget: about {item['probability']:.0f}% chance of going over this month "
            f"({item['remaining']:.2f} left; {_evidence(item)})"
        ),
    }


def generate_alerts(category_statuses: list[dict], period_status: dict | None, risk: dict | None = None) -> list[dict]:
    """Budget alerts. `risk` (see budget_risk) adds "likely to be exceeded" alerts and replaces the
    straight-line pace warning where there is enough history; without it the alerts are as before."""
    items = {i["category"]: i for i in (risk["items"] if risk else [])}
    alerts = [a for a in (_category_alert(s) for s in category_statuses) if a]
    if risk:
        alerts += [a for a in (_category_risk_alert(i) for i in items.values()) if a]
    predictive = _predictive_alert(period_status, items.get("Total"))
    if predictive:
        alerts.append(predictive)
    alerts.sort(key=lambda a: SEVERITY_RANK[a["severity"]], reverse=True)
    return alerts
