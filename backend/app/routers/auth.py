from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import jwt

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import User
from app.ratelimit import check_rate, client_ip
from app.schemas import LoginIn, TokenOut, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Used to keep login timing similar whether or not the email exists (avoids user enumeration).
_DUMMY_HASH = hash_password("not-a-real-password")


class GoogleTokenIn(BaseModel):
    access_token: str


@router.post("/google", response_model=TokenOut, summary="Sign in via Google / Supabase OAuth")
def google_login(body: GoogleTokenIn, db: Session = Depends(get_db)):
    """Exchange a Supabase access token for a TestPilot JWT."""
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise AppError(501, "not_configured", "Google login is not configured on this server")

    try:
        payload = jwt.decode(
            body.access_token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        raise AppError(401, "invalid_token", "Invalid or expired Google token")

    email = payload.get("email")
    if not email:
        raise AppError(401, "invalid_token", "Token does not contain an email address")

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        full_name = (payload.get("user_metadata") or {}).get("full_name") or email.split("@")[0]
        user = User(email=email, full_name=full_name, hashed_password="")
        db.add(user)
        db.commit()
        db.refresh(user)

    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=201, summary="Create an account")
def register(body: UserCreate, request: Request, db: Session = Depends(get_db)):
    check_rate("auth", client_ip(request), get_settings().rate_limit_auth_per_minute)
    if db.scalar(select(User).where(User.email == body.email)):
        raise AppError(409, "email_taken", "An account with this email already exists")
    user = User(email=body.email, full_name=body.full_name.strip(), hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut, summary="Sign in and receive a bearer token")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    check_rate("auth", client_ip(request), get_settings().rate_limit_auth_per_minute)
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.hashed_password if user else _DUMMY_HASH) or user is None:
        raise AppError(401, "invalid_credentials", "Incorrect email or password")
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="Current user")
def me(user: User = Depends(get_current_user)):
    return user
