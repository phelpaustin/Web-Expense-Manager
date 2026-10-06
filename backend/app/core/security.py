from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

_ALGORITHM = "HS256"
BCRYPT_MAX_PASSWORD_BYTES = 72


def validate_bcrypt_password(password: str) -> str:
    """Reject passwords bcrypt would reject or silently truncate."""
    try:
        encoded = password.encode("utf-8")
    except (AttributeError, UnicodeEncodeError) as exc:
        raise ValueError("Password must be valid UTF-8") from exc
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return password


def hash_password(password: str) -> str:
    validate_bcrypt_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        validate_bcrypt_password(password)
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except (ValueError, AttributeError, UnicodeEncodeError):
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


def create_email_verification_token(subject: str, verification_version: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "sub": subject,
        "exp": expire,
        "purpose": "verify_email",
        "email_verification_version": verification_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_email_verification_token(token: str) -> tuple[str, int] | None:
    """Return the subject and verification version for a valid token, else None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "verify_email":
        return None
    subject = payload.get("sub")
    version = payload.get("email_verification_version")
    if not isinstance(subject, str) or not isinstance(version, int) or isinstance(version, bool):
        return None
    return subject, version
