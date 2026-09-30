import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.email import send_email
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_reset_token,
    decode_reset_token,
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.db import models

router = APIRouter()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = ""


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str


class GoogleIn(BaseModel):
    credential: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class DeleteAccountIn(BaseModel):
    password: str


def _claim_group_invites(db: Session, user: models.User) -> None:
    """Add a newly-registered user to any groups they were invited to by email."""
    invites = db.query(models.GroupInvite).filter(models.GroupInvite.email == user.email).all()
    for invite in invites:
        already_member = (
            db.query(models.GroupMember)
            .filter(models.GroupMember.group_id == invite.group_id, models.GroupMember.user_id == user.id)
            .first()
        )
        if not already_member:
            db.add(models.GroupMember(group_id=invite.group_id, user_id=user.id, role=invite.role or "editor"))
        db.delete(invite)


@router.post("/auth/register", response_model=TokenOut, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, payload: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(models.User).filter(models.User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = models.User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        name=payload.name.strip(),
    )
    try:
        db.add(user)
        db.flush()
        _claim_group_invites(db, user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(user)

    return TokenOut(access_token=create_access_token(str(user.id), user.session_version))


@router.post("/auth/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenOut(access_token=create_access_token(str(user.id), user.session_version))


@router.get("/auth/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.post("/auth/google", response_model=TokenOut)
def google_login(payload: GoogleIn, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    # Imported lazily so the app runs without google-auth installed locally.
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(
            payload.credential, google_requests.Request(), settings.google_client_id
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = info.get("email")
    if not email or not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google account email not verified")

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        user = models.User(
            email=email,
            name=info.get("name", ""),
            # Random password — this account signs in via Google.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        try:
            db.add(user)
            db.flush()
            _claim_group_invites(db, user)
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(user)
    return TokenOut(access_token=create_access_token(str(user.id), user.session_version))


@router.post("/auth/logout", status_code=204)
def logout(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    user.session_version += 1
    db.commit()


@router.post("/auth/change-password")
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from the current one")
    user.hashed_password = hash_password(payload.new_password)
    user.session_version += 1
    db.commit()
    return {"changed": True}


@router.post("/auth/forgot-password")
@limiter.limit("5/hour")
def forgot_password(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Email a reset link. Always returns the same response (no user enumeration)."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user:
        token = create_reset_token(str(user.id), user.password_reset_version)
        link = f"{settings.frontend_url}/reset-password?token={token}"
        send_email(
            user.email,
            "Reset your Expense Dashboard password",
            f"We received a request to reset your password.\n\n"
            f"Open this link to choose a new password (valid for 30 minutes):\n{link}\n\n"
            f"If you didn't request this, you can ignore this email.",
        )
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/auth/reset-password")
@limiter.limit("10/hour")
def reset_password(request: Request, payload: ResetPasswordIn, db: Session = Depends(get_db)):
    decoded = decode_reset_token(payload.token)
    if decoded is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    subject, token_version = decoded
    user = db.get(models.User, int(subject))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    if token_version != user.password_reset_version:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from your old password")
    updated = (
        db.query(models.User)
        .filter(
            models.User.id == user.id,
            models.User.password_reset_version == token_version,
        )
        .update(
            {
                models.User.hashed_password: hash_password(payload.new_password),
                models.User.password_reset_version: models.User.password_reset_version + 1,
                models.User.session_version: models.User.session_version + 1,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    db.commit()
    return {"reset": True}


@router.post("/auth/delete-account", status_code=204)
def delete_account(
    payload: DeleteAccountIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    try:
        # Shared expenses are financial history: keep them but remove the deleted
        # account reference so they display as "Deleted user".
        db.query(models.Expense).filter(
            models.Expense.user_id == user.id,
            models.Expense.group_id.isnot(None),
        ).update({models.Expense.user_id: None}, synchronize_session=False)
        db.query(models.Expense).filter(
            models.Expense.user_id == user.id,
            models.Expense.group_id.is_(None),
        ).delete(synchronize_session=False)

        # Transfer owned spaces to an existing member when possible. An empty
        # space remains available as an ownerless historical container.
        owned_groups = db.query(models.Group).filter(models.Group.owner_id == user.id).all()
        for group in owned_groups:
            replacement = (
                db.query(models.GroupMember)
                .filter(
                    models.GroupMember.group_id == group.id,
                    models.GroupMember.user_id != user.id,
                )
                .order_by(models.GroupMember.id)
                .first()
            )
            if replacement is None:
                group.owner_id = None
            else:
                group.owner_id = replacement.user_id
                replacement.role = "owner"

        db.query(models.GroupMember).filter(models.GroupMember.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(models.GroupInvite).filter(
            (models.GroupInvite.invited_by == user.id) | (models.GroupInvite.email == user.email)
        ).delete(synchronize_session=False)

        # Receipts must be removed before their pending bills because the FK is
        # intentionally not configured with database-level cascade behavior.
        db.query(models.Receipt).filter(models.Receipt.user_id == user.id).delete(
            synchronize_session=False
        )
        for model in (
            models.Budget,
            models.Income,
            models.RecurringTemplate,
            models.PendingBill,
            models.ManualBill,
            models.UserOptions,
            models.Trip,
        ):
            db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)

        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise
