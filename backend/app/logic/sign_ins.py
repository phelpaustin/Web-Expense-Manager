"""Sign-in history: record who signed in (or failed to) and describe it for the Settings page."""
import datetime as dt
import re

from sqlalchemy.orm import Session

from app.db import models
from app.db.database import SessionLocal

KEEP_DAYS = 180
KEEP_ROWS = 500   # per account, newest first: a flood of failed attempts cannot grow the table
LIST_LIMIT = 50


def device_name(user_agent: str) -> str:
    """'Chrome on Mac' from a User-Agent string; empty when it says nothing useful."""
    ua = user_agent or ""
    if not ua:
        return ""
    if re.search(r"iPhone", ua):
        os_name = "iPhone"
    elif re.search(r"iPad", ua):
        os_name = "iPad"
    elif re.search(r"Android", ua):
        os_name = "Android"
    elif re.search(r"Windows", ua):
        os_name = "Windows"
    elif re.search(r"Macintosh|Mac OS X", ua):
        os_name = "Mac"
    elif re.search(r"CrOS", ua):
        os_name = "ChromeOS"
    elif re.search(r"Linux", ua):
        os_name = "Linux"
    else:
        os_name = ""
    if re.search(r"Edg/|EdgA/|EdgiOS/", ua):
        browser = "Edge"
    elif re.search(r"OPR/|Opera", ua):
        browser = "Opera"
    elif re.search(r"Firefox/|FxiOS/", ua):
        browser = "Firefox"
    elif re.search(r"Chrome/|CriOS/", ua):
        browser = "Chrome"
    elif re.search(r"Safari/", ua):
        browser = "Safari"
    elif re.search(r"curl/|python-requests|httpx|Postman", ua, re.I):
        browser = "Script"
    else:
        browser = ""
    return " on ".join(part for part in (browser, os_name) if part) or ua[:40]


def record_sign_in(user_id: int, method: str, success: bool, ip: str, user_agent: str) -> None:
    """Store one event. Runs after the response is sent, in its own session, so recording (or a
    failure to record) can never change what the visitor sees or how long a login takes."""
    try:
        with SessionLocal() as db:
            now = dt.datetime.now(dt.timezone.utc)
            db.add(models.SignInEvent(
                user_id=user_id, at=now, method=method, success=success,
                ip=(ip or "")[:64], user_agent=(user_agent or "")[:300],
            ))
            db.flush()
            _prune(db, user_id, now)
            db.commit()
    except Exception:  # noqa: BLE001 - history is best effort; never break a sign-in over it
        import logging

        logging.getLogger(__name__).warning("Could not record sign-in event", exc_info=True)


def _prune(db: Session, user_id: int, now: dt.datetime) -> None:
    db.query(models.SignInEvent).filter(
        models.SignInEvent.user_id == user_id, models.SignInEvent.at < now - dt.timedelta(days=KEEP_DAYS)
    ).delete(synchronize_session=False)
    cutoff = (
        db.query(models.SignInEvent.id)
        .filter(models.SignInEvent.user_id == user_id)
        .order_by(models.SignInEvent.id.desc())
        .offset(KEEP_ROWS)
        .limit(1)
        .scalar()
    )
    if cutoff is not None:
        db.query(models.SignInEvent).filter(
            models.SignInEvent.user_id == user_id, models.SignInEvent.id <= cutoff
        ).delete(synchronize_session=False)


def list_sign_ins(db: Session, user_id: int) -> dict:
    rows = (
        db.query(models.SignInEvent)
        .filter(models.SignInEvent.user_id == user_id)
        .order_by(models.SignInEvent.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )
    events = [
        {"at": r.at.isoformat(), "method": r.method, "success": r.success, "ip": r.ip, "device": device_name(r.user_agent)}
        for r in rows
    ]
    # Failed attempts since the last successful sign-in: the number worth a second look.
    recent_failures = 0
    for e in events:
        if e["success"]:
            break
        recent_failures += 1
    return {"events": events, "failed_since_last_success": recent_failures, "keep_days": KEEP_DAYS}
