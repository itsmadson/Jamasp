import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from agah.config import get_settings

ALGORITHM = "HS256"
SESSION_COOKIE = "agah_session"
TOKEN_TTL = timedelta(hours=12)


def _secret() -> str:
    secret = os.environ.get("AGAH_JWT_SECRET") or get_settings().jwt_secret
    if not secret:
        raise RuntimeError("AGAH_JWT_SECRET is not set; refusing to issue tokens")
    return secret


def issue_token(user_id: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(UTC) + TOKEN_TTL,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
