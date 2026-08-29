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


# Permission tiers for a member within a space: owner > admin > editor > viewer.
ROLES = ["owner", "admin", "editor", "viewer"]
_ROLE_RANK = {"owner": 3, "admin": 2, "editor": 1, "viewer": 0}


def get_membership(db: Session, group_id: int, user_id: int) -> models.GroupMember | None:
    return (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
    )


def role_at_least(db: Session, group_id: int, user_id: int, minimum: str) -> bool:
    """True if this user's role in the space is at or above `minimum` (e.g. 'editor')."""
    member = get_membership(db, group_id, user_id)
    if member is None:
        return False
    return _ROLE_RANK.get(member.role, 0) >= _ROLE_RANK.get(minimum, 0)


def require_role_at_least(db: Session, group_id: int, user_id: int, minimum: str, message: str) -> models.GroupMember:
    member = get_membership(db, group_id, user_id)
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this space")
    if _ROLE_RANK.get(member.role, 0) < _ROLE_RANK.get(minimum, 0):
        raise HTTPException(status_code=403, detail=message)
    return member
