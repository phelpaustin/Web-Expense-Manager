import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.email import send_email
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_reset_token,
    decode_email_verification_token,
    decode_reset_token,
    hash_password,
    validate_bcrypt_password,
    verify_password,
)
from app.db.database import get_db
from app.db import models

router = APIRouter()
PASSWORD_MIN_LENGTH = 12
PasswordInput = Annotated[str, BeforeValidator(validate_bcrypt_password)]


class RegisterIn(BaseModel):
    email: EmailStr


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegistrationOut(BaseModel):
    verification_required: bool = True
    message: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str


class GoogleIn(BaseModel):
    credential: str


class PasswordChange(BaseModel):
    current_password: PasswordInput
    new_password: PasswordInput = Field(min_length=PASSWORD_MIN_LENGTH)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class VerifyEmailIn(BaseModel):
    token: str
    name: str = ""
    new_password: PasswordInput = Field(min_length=PASSWORD_MIN_LENGTH)


class ResetPasswordIn(BaseModel):
    token: str
    new_password: PasswordInput = Field(min_length=PASSWORD_MIN_LENGTH)


class DeleteAccountIn(BaseModel):
    password: PasswordInput


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
            role = invite.role if invite.role in ("admin", "editor", "viewer") else "editor"
            db.add(models.GroupMember(group_id=invite.group_id, user_id=user.id, role=role))
        db.delete(invite)


def _send_verification_email(user: models.User) -> bool:
    token = create_email_verification_token(str(user.id), user.email_verification_version)
    link = f"{settings.frontend_url.rstrip('/')}/verify-email?token={token}"
    return send_email(
        user.email,
        "Verify your Expense Dashboard email",
        "Please verify that this email address belongs to you.\n\n"
        f"Open this link and confirm verification within 24 hours:\n{link}\n\n"
        "If you did not create this account, you can ignore this message.",
    )


@router.post("/auth/register", response_model=RegistrationOut, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, payload: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(models.User).filter(models.User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = models.User(
        email=payload.email,
        # Never bind a password chosen before the address is verified. The
        # mailbox owner chooses the credential when completing verification.
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        name="",
        email_verified=False,
    )
    try:
        db.add(user)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(user)

    _send_verification_email(user)
    return RegistrationOut(message="Account created. Check your email for a verification link before signing in.")


@router.post("/auth/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before signing in")
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
            email_verified=True,
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
    elif not user.email_verified:
        # Google's verified email is proof of ownership for an existing local
        # account too; use it to complete verification and claim pending invites.
        try:
            user.email_verified = True
            user.email_verification_version += 1
            user.name = user.name or info.get("name", "")
            _claim_group_invites(db, user)
            db.commit()
        except Exception:
            db.rollback()
            raise
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


@router.post("/auth/resend-verification")
@limiter.limit("5/hour")
def resend_verification(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Resend a verification link without revealing whether the account exists."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user is not None and not user.email_verified:
        user.email_verification_version += 1
        db.commit()
        _send_verification_email(user)
    return {"message": "If that account needs verification, a new link has been sent."}


@router.post("/auth/verify-email")
@limiter.limit("20/hour")
def verify_email(request: Request, payload: VerifyEmailIn, db: Session = Depends(get_db)):
    decoded = decode_email_verification_token(payload.token)
    if decoded is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    subject, token_version = decoded
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link") from exc

    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if user.email_verified:
        return {"verified": True}
    if token_version != user.email_verification_version:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    try:
        updated = (
            db.query(models.User)
            .filter(
                models.User.id == user_id,
                models.User.email_verified.is_(False),
                models.User.email_verification_version == token_version,
            )
            .update(
                {
                    models.User.email_verified: True,
                    models.User.email_verification_version: models.User.email_verification_version + 1,
                    models.User.hashed_password: hash_password(payload.new_password),
                    models.User.name: payload.name.strip(),
                    models.User.session_version: models.User.session_version + 1,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            current = db.get(models.User, user_id)
            if current is not None and current.email_verified:
                return {"verified": True}
            raise HTTPException(status_code=400, detail="Invalid or expired verification link")
        user = db.get(models.User, user_id)
        _claim_group_invites(db, user)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    return {"verified": True}


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
                models.User.email_verified: True,
                models.User.email_verification_version: models.User.email_verification_version + 1,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    try:
        user.email_verified = True
        _claim_group_invites(db, user)
        db.commit()
    except Exception:
        db.rollback()
        raise
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
