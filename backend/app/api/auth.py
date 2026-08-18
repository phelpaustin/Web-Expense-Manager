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


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


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


@router.post("/auth/register", response_model=TokenOut, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, payload: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(models.User).filter(models.User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = models.User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/auth/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/auth/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password")
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"changed": True}


@router.post("/auth/forgot-password")
@limiter.limit("5/hour")
def forgot_password(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Email a reset link. Always returns the same response (no user enumeration)."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user:
        token = create_reset_token(str(user.id))
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
    subject = decode_reset_token(payload.token)
    if subject is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user = db.get(models.User, int(subject))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user.hashed_password = hash_password(payload.new_password)
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
    for model in (
        models.Expense,
        models.Budget,
        models.Income,
        models.RecurringTemplate,
        models.PendingBill,
        models.ManualBill,
        models.UserOptions,
    ):
        db.query(model).filter(model.user_id == user.id).delete()
    db.delete(user)
    db.commit()
