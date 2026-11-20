"""Password hashing, JWT access tokens and API-key helpers."""

import hashlib
import secrets
from datetime import timedelta

import bcrypt
import jwt

from app.config import get_settings
from app.errors import AppError
from app.utils import utcnow

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AppError(401, "token_expired", "Session expired, please sign in again") from None
    except jwt.InvalidTokenError:
        raise AppError(401, "invalid_token", "Invalid authentication token") from None


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, sha256 hash). The plaintext is shown exactly once."""
    plaintext = "tp_" + secrets.token_urlsafe(32)
    return plaintext, plaintext[:10], hash_api_key(plaintext)


def hash_api_key(key: str) -> str:
    # High-entropy random key => a fast hash is appropriate (no need for bcrypt).
    return hashlib.sha256(key.encode()).hexdigest()
