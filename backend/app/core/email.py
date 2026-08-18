"""Minimal email sending via SMTP (stdlib only).

If SMTP is not configured (no SMTP_HOST), the message is logged to the server
console instead — so password reset still works in local dev.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("email")


def send_email(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        log.warning("SMTP not configured — email to %s not sent.\nSubject: %s\n%s", to, subject, body)
        return False

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    return True
