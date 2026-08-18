"""Email sending — Resend HTTP API (preferred) or SMTP fallback.

Order of preference:
  1. RESEND_API_KEY set → send via Resend's HTTPS API (works even where
     outbound SMTP ports are blocked, e.g. Render).
  2. SMTP_HOST set → send via SMTP.
  3. Neither → log the message to the console (fine for local dev).
"""
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("email")

_RESEND_ENDPOINT = "https://api.resend.com/emails"


def _from_address() -> str:
    return settings.email_from or settings.smtp_from or "onboarding@resend.dev"


def _send_via_resend(to: str, subject: str, body: str) -> bool:
    payload = json.dumps(
        {"from": _from_address(), "to": [to], "subject": subject, "text": body}
    ).encode()
    req = urllib.request.Request(
        _RESEND_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        log.error("Resend API error %s: %s", exc.code, exc.read().decode(errors="ignore"))
        return False
    except Exception:
        log.exception("Failed to send email to %s via Resend", to)
        return False


def _send_via_smtp(to: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = _from_address()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 — never let email failure break the caller
        log.exception("Failed to send email to %s via SMTP", to)
        return False


def send_email(to: str, subject: str, body: str) -> bool:
    if settings.resend_api_key:
        return _send_via_resend(to, subject, body)
    if settings.smtp_host:
        return _send_via_smtp(to, subject, body)
    log.warning("Email not configured — message to %s not sent.\nSubject: %s\n%s", to, subject, body)
    return False

