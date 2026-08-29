from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_group_ids, is_group_member
from app.db.database import get_db
from app.db import models

router = APIRouter()

SPACE_TYPES = ["household", "business", "rental", "trip", "custom"]
SPACE_TYPE_LABELS = {
    "household": "Household",
    "business": "Business",
    "rental": "Rental",
    "trip": "Trip",
    "custom": "Custom",
}


class GroupCreate(BaseModel):
    name: str = Field(min_length=1)
    space_type: str = "custom"


class GroupUpdate(BaseModel):
    name: str = Field(min_length=1)
    space_type: str | None = None


class InviteIn(BaseModel):
    email: EmailStr


def _group_or_404(db: Session, group_id: int) -> models.Group:
    group = db.get(models.Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _require_member(db: Session, group_id: int, user_id: int) -> models.GroupMember:
    member = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    return member


def _require_owner(db: Session, group_id: int, user_id: int) -> models.GroupMember:
    member = _require_member(db, group_id, user_id)
    if member.role != "owner":
        raise HTTPException(status_code=403, detail="Only the group owner can do this")
    return member


def _serialize_group(db: Session, group: models.Group, role: str) -> dict:
    member_count = db.query(models.GroupMember).filter(models.GroupMember.group_id == group.id).count()
    return {
        "id": group.id,
        "name": group.name,
        "space_type": group.space_type,
        "space_type_label": SPACE_TYPE_LABELS.get(group.space_type, "Custom"),
        "role": role,
        "member_count": member_count,
    }


@router.get("/groups")
def list_groups(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    memberships = db.query(models.GroupMember).filter(models.GroupMember.user_id == user.id).all()
    groups = []
    for m in memberships:
        group = db.get(models.Group, m.group_id)
        if group:
            groups.append(_serialize_group(db, group, m.role))
    return groups


@router.post("/groups", status_code=201)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    space_type = payload.space_type if payload.space_type in SPACE_TYPES else "custom"
    group = models.Group(owner_id=user.id, name=payload.name.strip(), space_type=space_type)
    db.add(group)
    db.flush()
    db.add(models.GroupMember(group_id=group.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(group)
    return _serialize_group(db, group, "owner")


@router.put("/groups/{group_id}")
def rename_group(
    group_id: int,
    payload: GroupUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    group = _group_or_404(db, group_id)
    member = _require_owner(db, group_id, user.id)
    group.name = payload.name.strip()
    if payload.space_type and payload.space_type in SPACE_TYPES:
        group.space_type = payload.space_type
    db.commit()
    return _serialize_group(db, group, member.role)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    group = _group_or_404(db, group_id)
    _require_owner(db, group_id, user.id)
    # Keep the expenses, just detach them from the deleted group.
    db.query(models.Expense).filter(models.Expense.group_id == group.id).update({"group_id": None})
    db.query(models.GroupMember).filter(models.GroupMember.group_id == group.id).delete()
    db.query(models.GroupInvite).filter(models.GroupInvite.group_id == group.id).delete()
    db.delete(group)
    db.commit()


@router.get("/groups/{group_id}/members")
def list_members(
    group_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _group_or_404(db, group_id)
    _require_member(db, group_id, user.id)
    members = db.query(models.GroupMember).filter(models.GroupMember.group_id == group_id).all()
    result = []
    for m in members:
        u = db.get(models.User, m.user_id)
        result.append({"user_id": m.user_id, "email": u.email if u else "", "name": u.name if u else "", "role": m.role})
    pending = db.query(models.GroupInvite).filter(models.GroupInvite.group_id == group_id).all()
    for inv in pending:
        result.append({"user_id": None, "email": inv.email, "name": "", "role": "invited"})
    return result


@router.post("/groups/{group_id}/invite", status_code=201)
def invite_member(
    group_id: int,
    payload: InviteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _group_or_404(db, group_id)
    _require_owner(db, group_id, user.id)

    invitee = db.query(models.User).filter(models.User.email == payload.email).first()
    if invitee:
        if is_group_member(db, group_id, invitee.id):
            raise HTTPException(status_code=409, detail="That user is already a member")
        db.add(models.GroupMember(group_id=group_id, user_id=invitee.id, role="member"))
        db.commit()
        return {"status": "added", "email": payload.email}

    existing_invite = (
        db.query(models.GroupInvite)
        .filter(models.GroupInvite.group_id == group_id, models.GroupInvite.email == payload.email)
        .first()
    )
    if existing_invite:
        raise HTTPException(status_code=409, detail="Already invited — waiting for them to sign up")
    db.add(models.GroupInvite(group_id=group_id, email=payload.email, invited_by=user.id))
    db.commit()
    return {"status": "pending", "email": payload.email}


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
def remove_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _group_or_404(db, group_id)
    _require_owner(db, group_id, user.id)
    target = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the group owner")
    db.delete(target)
    db.commit()


@router.delete("/groups/{group_id}/invites/{email}", status_code=204)
def cancel_invite(
    group_id: int,
    email: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _group_or_404(db, group_id)
    _require_owner(db, group_id, user.id)
    db.query(models.GroupInvite).filter(
        models.GroupInvite.group_id == group_id, models.GroupInvite.email == email
    ).delete()
    db.commit()


@router.post("/groups/{group_id}/leave", status_code=204)
def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    member = _require_member(db, group_id, user.id)
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="The owner can't leave — delete the group instead")
    db.delete(member)
    db.commit()
