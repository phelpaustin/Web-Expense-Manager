"""Budget alert generation — a thin layer over budgets_logic's status calculations.

No persistence: alerts are recomputed from current budget/spending state on
every request, so there's nothing to keep in sync or clean up.
"""
from __future__ import annotations

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


def _predictive_alert(period_status: dict | None) -> dict | None:
    """Warn when the current pace projects to exceed the period budget, even if not there yet."""
    if not period_status:
        return None
    effective = period_status["effective"]
    projected = period_status["projected"]
    if effective <= 0 or projected <= effective or period_status["pct"] >= 100:
        return None
    over_by = projected - effective
    return {
        "id": "predictive:period",
        "severity": "warning",
        "category": "Total",
        "message": (
            f"On pace to spend {projected:.2f} this {period_status['period'].lower()} "
            f"— {over_by:.2f} over your {effective:.2f} budget"
        ),
    }


def generate_alerts(category_statuses: list[dict], period_status: dict | None) -> list[dict]:
    alerts = [a for a in (_category_alert(s) for s in category_statuses) if a]
    predictive = _predictive_alert(period_status)
    if predictive:
        alerts.append(predictive)
    alerts.sort(key=lambda a: SEVERITY_RANK[a["severity"]], reverse=True)
    return alerts
