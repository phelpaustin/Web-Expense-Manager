from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password, verify_password
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
