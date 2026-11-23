import logging
from functools import lru_cache

import httpx
import jwt
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import User
from app.ratelimit import check_rate, client_ip
from app.schemas import LoginIn, TokenOut, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

logger = logging.getLogger("testpilot.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Used to keep login timing similar whether or not the email exists (avoids user enumeration).
_DUMMY_HASH = hash_password("not-a-real-password")


class GoogleTokenIn(BaseModel):
    access_token: str


@lru_cache(maxsize=4)
def _get_jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def _verify_supabase_token(token: str, supabase_url: str, anon_key: str) -> dict:
    """Verify Supabase JWT. First tries local cryptographic verification via JWKS (no rate limits).
    Falls back to Supabase's /auth/v1/user endpoint if needed.
    """
    # 1. Try local JWKS verification (cached, ultra-fast, zero rate-limit issues)
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        client = _get_jwk_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            options={"verify_aud": False},
        )
        if payload.get("email"):
            return payload
    except Exception as exc:
        logger.info("JWKS verification unsuccessful (%s), trying /auth/v1/user fallback", exc)

    # 2. Fallback: ask Supabase directly
    try:
        resp = httpx.get(
            f"{supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": anon_key,
            },
            timeout=10,
        )
    except httpx.RequestError as exc:
        raise AppError(503, "upstream_error", "Could not reach Supabase to verify token") from exc

    if resp.status_code == 429:
        logger.warning("Supabase /auth/v1/user rate limit exceeded")
        raise AppError(429, "rate_limited", "Authentication rate limit reached. Please wait a minute and try again.")
    if resp.status_code != 200:
        logger.warning("Supabase token verification failed: HTTP %s - %s", resp.status_code, resp.text)
        raise AppError(401, "invalid_token", "Invalid or expired Google token")

    return resp.json()


@router.post("/google", response_model=TokenOut, summary="Sign in via Google / Supabase OAuth")
def google_login(body: GoogleTokenIn, db: Session = Depends(get_db)):
    """Exchange a Supabase access token for a TestPilot JWT."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise AppError(501, "not_configured", "Google login is not configured on this server")

    user_data = _verify_supabase_token(body.access_token, settings.supabase_url, settings.supabase_anon_key)

    email = user_data.get("email")
    if not email:
        raise AppError(401, "invalid_token", "Token does not contain an email address")

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        meta = user_data.get("user_metadata") or {}
        full_name = meta.get("full_name") or meta.get("name") or email.split("@")[0]
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
