"""Custom SQLAlchemy column types."""

import base64
import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, Text
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class UTCDateTime(TypeDecorator):
    """Always store UTC and always return timezone-aware datetimes.

    SQLite drops tzinfo; PostgreSQL keeps it. Normalising here means the rest of
    the code never has to care which database is underneath.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


class EncryptedJSON(TypeDecorator):
    """JSON value encrypted at rest (Fernet / AES-128-CBC + HMAC).

    Used for credentials (auth configs, project variables) so a database dump does
    not leak bearer tokens or passwords in clear text.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        return _fernet().encrypt(json.dumps(value).encode()).decode()

    def process_result_value(self, value: str | None, dialect):
        if value is None:
            return None
        try:
            return json.loads(_fernet().decrypt(value.encode()).decode())
        except InvalidToken:  # key rotated or corrupted data: fail closed
            return {}
