from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.database import get_db
from app.db import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    subject = decode_token(token)
    if subject is None:
        raise credentials_exc
    user = db.get(models.User, int(subject))
    if user is None:
        raise credentials_exc
    return user


def get_user_group_ids(db: Session, user_id: int) -> list[int]:
    """IDs of every group (household/business/...) this user belongs to."""
    rows = db.query(models.GroupMember.group_id).filter(models.GroupMember.user_id == user_id).all()
    return [r[0] for r in rows]


def is_group_member(db: Session, group_id: int, user_id: int) -> bool:
    return (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
        is not None
    )
