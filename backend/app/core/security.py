from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(subject: str, session_version: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "session_version": session_version}
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> tuple[str, int] | None:
    """Return the token's subject and session version if valid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    session_version = payload.get("session_version")
    if (
        not isinstance(subject, str)
        or not isinstance(session_version, int)
        or isinstance(session_version, bool)
    ):
        return None
    return subject, session_version


def create_reset_token(subject: str, password_reset_version: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {
        "sub": subject,
        "exp": expire,
        "purpose": "reset",
        "password_reset_version": password_reset_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_reset_token(token: str) -> tuple[str, int] | None:
    """Return the subject and reset version for a valid reset token, else None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "reset":
        return None
    subject = payload.get("sub")
    version = payload.get("password_reset_version")
    if not isinstance(subject, str) or not isinstance(version, int) or isinstance(version, bool):
        return None
    return subject, version
