import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from jamasp.config import get_settings

ALGORITHM = "HS256"
SESSION_COOKIE = "jamasp_session"
TOKEN_TTL = timedelta(hours=12)


def _secret() -> str:
    secret = os.environ.get("JAMASP_JWT_SECRET") or get_settings().jwt_secret
    if not secret:
        raise RuntimeError("JAMASP_JWT_SECRET is not set; refusing to issue tokens")
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
