"""Email address normalisation: addresses are compared case-insensitively.

`Alice@Example.com` and `alice@example.com` are the same mailbox in practice, so a
person who signs up one way and signs in the other must reach the same account.
New data is stored lowercase; lookups also match on lower(column) so accounts that
predate normalisation (and could not be merged automatically) still resolve.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import models


def normalize_email(value: str) -> str:
    return value.strip().lower()


# Use in request schemas instead of a bare EmailStr.
NormalizedEmail = Annotated[EmailStr, AfterValidator(normalize_email)]


def user_by_email(db: Session, email: str) -> models.User | None:
    # Oldest account wins if legacy rows differ only by case.
    return (
        db.query(models.User)
        .filter(func.lower(models.User.email) == normalize_email(email))
        .order_by(models.User.id)
        .first()
    )
