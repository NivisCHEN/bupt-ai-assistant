"""Authentication stub — returns a fixed default user.

Token validation is disabled. All requests are treated as coming from
``default_user``.
"""

from __future__ import annotations

_DEFAULT_USER = "default_user"


def generate_token(user_id: str) -> str:
    """Return a dummy token (authentication disabled)."""
    return f"{user_id}:no-auth"


def verify_token(token: str) -> str:
    """Return the default user id (authentication disabled)."""
    return _DEFAULT_USER


async def validate_user_token() -> str:
    """FastAPI dependency — always returns the default user id."""
    return _DEFAULT_USER
