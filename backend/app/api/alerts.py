import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.budgets import fetch_budgets
from app.api.options import get_or_create_options
from app.api.expenses import fetch_expenses_in_reporting_currency
from app.core.config import settings
from app.core.email import send_email
from app.db.database import get_db
from app.db import models
from app.logic import alerts as alerts_logic
from app.logic import budgets as budgets_logic
from app.logic.budgets import TOTAL_BUDGET_KEY

router = APIRouter()
log = logging.getLogger("alerts")


def _alerts_for_user(db: Session, user_id: int) -> list[dict]:
    expenses = fetch_expenses_in_reporting_currency(db, user_id)
    budgets = fetch_budgets(db, user_id)
    opts = get_or_create_options(db, user_id)

    category_statuses = budgets_logic.calculate_budget_status(expenses, budgets)
    period_status = budgets_logic.period_budget_status(
        expenses, budgets.get(TOTAL_BUDGET_KEY), opts.budget_period, opts.budget_rollover
    )
    return alerts_logic.generate_alerts(category_statuses, period_status)


@router.get("/alerts")
def get_alerts(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return _alerts_for_user(db, user.id)


def _digest_body(alerts: list[dict]) -> str:
    lines = [f"- [{a['severity'].upper()}] {a['message']}" for a in alerts]
    return "Your budget alerts:\n\n" + "\n".join(lines)


def _digest_signature(alerts: list[dict]) -> str:
    """Fingerprint active alert identities and severities, not changing amounts."""
    active = sorted((str(alert.get("id", "")), str(alert.get("severity", ""))) for alert in alerts)
    payload = json.dumps(active, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@router.post("/alerts/send-digest")
def send_alert_digest(
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Email every user their current budget alerts (if any). Meant to be called
    by an external scheduler (e.g. a daily GitHub Actions cron), not the frontend —
    protected by a shared secret instead of a user login.
    """
    if not settings.cron_secret or not hmac.compare_digest(
        x_cron_secret.encode(), settings.cron_secret.encode()
    ):
        raise HTTPException(status_code=403, detail="Invalid or missing cron secret")

    sent, skipped, failed = 0, 0, 0
    for user in db.query(models.User).all():
        # One user's problem (bad data, FX outage, email error) must not stop
        # the digest for everyone else.
        try:
            alerts = _alerts_for_user(db, user.id)
            if not alerts:
                if user.alert_digest_signature is not None:
                    user.alert_digest_signature = None
                    db.commit()
                skipped += 1
                continue
            signature = _digest_signature(alerts)
            if signature == user.alert_digest_signature:
                skipped += 1
                continue
            if send_email(user.email, "Your budget alerts", _digest_body(alerts)):
                user.alert_digest_signature = signature
                db.commit()
                sent += 1
            else:
                skipped += 1
        except Exception:  # noqa: BLE001 — isolate per-user failures
            db.rollback()
            failed += 1
            log.exception("Alert digest failed for user id=%s", user.id)
    return {"users_emailed": sent, "users_skipped": skipped, "users_failed": failed}
