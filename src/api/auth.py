"""HMAC-signed token authentication for user identity verification.

Tokens encode the user_id and a timestamp, signed with a shared secret.
This prevents forged tokens and enforces per-user access control on
memory endpoints.
"""

from __future__ import annotations

import hmac
import hashlib
import os
import time
import warnings

from fastapi import HTTPException, Header


# The secret MUST be set in production via the USER_TOKEN_SECRET env var.
_SECRET = os.getenv("USER_TOKEN_SECRET", "")

if not _SECRET:
    warnings.warn(
        "USER_TOKEN_SECRET is not set — token authentication is insecure! "
        "Set this environment variable before deploying to production.",
        stacklevel=1,
    )

# Token validity window in seconds (default 24 hours).
_TOKEN_TTL = int(os.getenv("USER_TOKEN_TTL", "86400"))


def generate_token(user_id: str) -> str:
    """Generate an HMAC-signed token for *user_id*.

    Format: ``{user_id}:{unix_timestamp}:{hex_signature}``
    """
    ts = int(time.time())
    payload = f"{user_id}:{ts}"
    sig = hmac.new(
        _SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{sig}"


def verify_token(token: str) -> str:
    """Verify an HMAC-signed token and return the embedded *user_id*.

    Raises:
        HTTPException: 401 if the token is malformed, has an invalid
            signature, or has expired.
    """
    try:
        user_id, ts_str, sig = token.rsplit(":", 2)
        expected = hmac.new(
            _SECRET.encode(),
            f"{user_id}:{ts_str}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        if _TOKEN_TTL > 0 and int(time.time()) - int(ts_str) > _TOKEN_TTL:
            raise ValueError("expired")
        return user_id
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def validate_user_token(
    x_user_token: str = Header(..., description="HMAC-signed user token"),
) -> str:
    """FastAPI dependency that validates the ``X-User-Token`` header.

    Returns the authenticated *user_id* extracted from the token.
    """
    return verify_token(x_user_token)
