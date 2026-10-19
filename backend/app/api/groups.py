from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    is_group_member,
    require_role_at_least,
)
from app.api.options import default_currency_for
from app.core.config import settings
from app.core.email import send_email
from app.core.emails import NormalizedEmail, normalize_email, user_by_email
from app.core.fx import normalize_convertible_currency
from app.core.rate_limit import limiter
from app.core.validation import Name, OptionalName
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


def _validate_optional_currency(value: str | None) -> str | None:
    return normalize_convertible_currency(value) if value is not None else None


class GroupCreate(BaseModel):
    name: Name
    space_type: str = "custom"
    # Default currency for new expenses in this space; None = the creator's base currency.
    currency: str | None = None

    check_currency = field_validator("currency")(lambda cls, v: _validate_optional_currency(v))


class GroupUpdate(BaseModel):
    name: Name
    space_type: str | None = None
    # Only changes the default for *new* expenses; existing expenses keep their own currency.
    currency: str | None = None

    check_currency = field_validator("currency")(lambda cls, v: _validate_optional_currency(v))


class InviteIn(BaseModel):
    email: NormalizedEmail
    role: str = "editor"  # admin | editor | viewer (owner is not invitable)


class RoleChangeIn(BaseModel):
    role: str


class MyMappingIn(BaseModel):
    local_name: OptionalName | None = None
    local_parent_group_id: int | None = None


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


def _serialize_group(db: Session, group: models.Group, member: models.GroupMember) -> dict:
    member_count = db.query(models.GroupMember).filter(models.GroupMember.group_id == group.id).count()
    return {
        "id": group.id,
        "name": member.local_name or group.name,
        "space_type": group.space_type,
        "space_type_label": SPACE_TYPE_LABELS.get(group.space_type, "Custom"),
        "currency": group.currency or "SEK",
        "parent_group_id": group.parent_group_id,
        "local_name": member.local_name,
        "local_parent_group_id": member.local_parent_group_id,
        "role": member.role,
        "member_count": member_count,
    }


def _invitation_message(email: str, group_name: str, inviter: str, role: str, has_account: bool) -> tuple[str, str, str]:
    link = f"{settings.frontend_url.rstrip('/')}/groups"
    what = (
        f"Sign in and open Groups to accept or decline: {link}"
        if has_account
        else f"Create an account with this email address ({link.rsplit('/', 1)[0]}/) and you will be added automatically."
    )
    return (
        email,
        f"{inviter} invited you to \"{group_name}\"",
        f"{inviter} invited you to join the shared space \"{group_name}\" on Expense Dashboard as {role}.\n\n"
        f"{what}\n\nIf you don't know {inviter}, you can ignore this message.",
    )


# Declared before the /groups/{group_id} routes so "invitations" is not read as an id.
@router.get("/groups/invitations")
def my_invitations(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Invitations to join a space that are waiting for the signed-in user to accept or decline."""
    rows = (
        db.query(models.GroupInvite, models.Group, models.User)
        .join(models.Group, models.Group.id == models.GroupInvite.group_id)
        .outerjoin(models.User, models.User.id == models.GroupInvite.invited_by)
        .filter(func.lower(models.GroupInvite.email) == normalize_email(user.email))
        .order_by(models.GroupInvite.id)
        .all()
    )
    return [
        {
            "id": inv.id,
            "group_id": g.id,
            "group_name": g.name,
            "role": inv.role,
            "invited_by": (inviter.name or inviter.email) if inviter else "Someone",
        }
        for inv, g, inviter in rows
    ]


def _my_invite_or_404(db: Session, invite_id: int, user: models.User) -> models.GroupInvite:
    inv = db.get(models.GroupInvite, invite_id)
    if inv is None or normalize_email(inv.email) != normalize_email(user.email):
        raise HTTPException(status_code=404, detail="Invitation not found")
    return inv


@router.post("/groups/invitations/{invite_id}/accept")
def accept_invitation(invite_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    inv = _my_invite_or_404(db, invite_id, user)
    group = db.get(models.Group, inv.group_id)
    if group is None:
        db.delete(inv)
        db.commit()
        raise HTTPException(status_code=404, detail="That space no longer exists")
    if not is_group_member(db, group.id, user.id):
        role = inv.role if inv.role in ("admin", "editor", "viewer") else "editor"
        db.add(models.GroupMember(group_id=group.id, user_id=user.id, role=role))
    db.delete(inv)
    db.commit()
    return {"group_id": group.id}


@router.post("/groups/invitations/{invite_id}/decline", status_code=204)
def decline_invitation(invite_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db.delete(_my_invite_or_404(db, invite_id, user))
    db.commit()


@router.get("/groups")
def list_groups(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    memberships = db.query(models.GroupMember).filter(models.GroupMember.user_id == user.id).all()
    groups = []
    for m in memberships:
        group = db.get(models.Group, m.group_id)
        if group and group.space_type != "trip":
            groups.append(_serialize_group(db, group, m))
    return groups


@router.post("/groups", status_code=201)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    space_type = payload.space_type if payload.space_type in SPACE_TYPES else "custom"
    if space_type == "trip":
        raise HTTPException(status_code=400, detail="Create trips from the Trips page instead")
    group = models.Group(
        owner_id=user.id,
        name=payload.name.strip(),
        space_type=space_type,
        currency=payload.currency or default_currency_for(db, user.id),
    )
    db.add(group)
    db.flush()
    member = models.GroupMember(group_id=group.id, user_id=user.id, role="owner")
    db.add(member)
    db.commit()
    db.refresh(group)
    return _serialize_group(db, group, member)


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
    if payload.currency:
        group.currency = payload.currency
    if payload.space_type and payload.space_type in SPACE_TYPES and payload.space_type != "trip":
        group.space_type = payload.space_type
    db.commit()
    return _serialize_group(db, group, member)


@router.put("/groups/{group_id}/my-mapping")
def set_my_mapping(
    group_id: int,
    payload: MyMappingIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Let a member file a shared space under their own space and/or rename it locally,
    without touching the owner's structure or other members' views."""
    group = _group_or_404(db, group_id)
    member = _require_member(db, group_id, user.id)
    if payload.local_parent_group_id is not None:
        if not is_group_member(db, payload.local_parent_group_id, user.id):
            raise HTTPException(status_code=400, detail="You can only map to a space you belong to")
    member.local_name = (payload.local_name or "").strip() or None
    member.local_parent_group_id = payload.local_parent_group_id
    db.commit()
    return _serialize_group(db, group, member)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    group = _group_or_404(db, group_id)
    _require_owner(db, group_id, user.id)
    cascade_delete_group(db, group)
    db.commit()


def detach_member(db: Session, group_id: int, user_id: int) -> int:
    """Take a user out of a space/trip without orphaning their data.

    Their expenses in the space go back to being personal (they stay theirs and stay
    editable; otherwise they would be tagged to a space they can no longer open, and a
    trip's settlement would count them with no payer). Their own mappings into this
    space as a local parent are cleared. Returns how many expenses were moved.
    """
    moved = (
        db.query(models.Expense)
        .filter(models.Expense.group_id == group_id, models.Expense.user_id == user_id)
        .update({"group_id": None}, synchronize_session=False)
    )
    db.query(models.GroupMember).filter(
        models.GroupMember.user_id == user_id, models.GroupMember.local_parent_group_id == group_id
    ).update({"local_parent_group_id": None}, synchronize_session=False)
    db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id
    ).delete(synchronize_session=False)
    return moved


def cascade_delete_group(db: Session, group: models.Group) -> None:
    """Detach the group's expenses (kept, just un-tagged), un-nest any child trips/spaces,
    clear any member's local mapping pointing at it, and remove its members/invites/self."""
    db.query(models.Expense).filter(models.Expense.group_id == group.id).update({"group_id": None})
    db.query(models.Group).filter(models.Group.parent_group_id == group.id).update({"parent_group_id": None})
    db.query(models.GroupMember).filter(models.GroupMember.local_parent_group_id == group.id).update(
        {"local_parent_group_id": None}
    )
    db.query(models.GroupMember).filter(models.GroupMember.group_id == group.id).delete()
    db.query(models.GroupInvite).filter(models.GroupInvite.group_id == group.id).delete()
    db.delete(group)


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
@limiter.limit("20/hour")
def invite_member(
    request: Request,
    background: BackgroundTasks,
    group_id: int,
    payload: InviteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _group_or_404(db, group_id)
    require_role_at_least(db, group_id, user.id, "admin", "Only owners and admins can invite members")

    role = payload.role if payload.role in ("admin", "editor", "viewer") else "editor"

    # The answer must not depend on whether the address has an account: everyone is invited the
    # same way and chooses to accept (an account holder on the Groups page, a new user by signing
    # up). Otherwise inviting arbitrary addresses would be a way to find out who is registered,
    # and would add people to a space without their say.
    invitee = user_by_email(db, payload.email)
    if invitee and is_group_member(db, group_id, invitee.id):
        # The inviter can already see this person in the member list, so this tells them nothing new.
        raise HTTPException(status_code=409, detail="That person is already a member")
    existing_invite = (
        db.query(models.GroupInvite)
        .filter(models.GroupInvite.group_id == group_id, func.lower(models.GroupInvite.email) == payload.email)
        .first()
    )
    if existing_invite is None:
        db.add(models.GroupInvite(group_id=group_id, email=payload.email, invited_by=user.id, role=role))
        db.commit()
        group = db.get(models.Group, group_id)
        background.add_task(
            send_email,
            *_invitation_message(payload.email, group.name, user.name or user.email, role, invitee is not None),
        )
    return {"status": "pending", "email": payload.email, "role": role}


@router.put("/groups/{group_id}/members/{user_id}/role")
def change_member_role(
    group_id: int,
    user_id: int,
    payload: RoleChangeIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _group_or_404(db, group_id)
    _require_owner(db, group_id, user.id)
    if payload.role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be admin, editor, or viewer")
    target = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot change the owner's role")
    target.role = payload.role
    db.commit()
    return {"user_id": user_id, "role": target.role}


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
    detach_member(db, group_id, user_id)
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
        models.GroupInvite.group_id == group_id,
        func.lower(models.GroupInvite.email) == normalize_email(email),
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
    detach_member(db, group_id, user.id)
    db.commit()
