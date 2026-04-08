"""Tests for authentication stub (login disabled)."""

import pytest

from src.api.auth import generate_token, verify_token, validate_user_token


class TestTokenGeneration:

    def test_generate_token_returns_string(self):
        token = generate_token("user1")
        assert isinstance(token, str)
        assert "user1" in token

    def test_generate_token_contains_user_id(self):
        token = generate_token("test-user")
        assert "test-user" in token


class TestTokenVerification:

    def test_verify_always_returns_default_user(self):
        assert verify_token("anything") == "default_user"

    def test_verify_empty_token(self):
        assert verify_token("") == "default_user"

    def test_verify_ignores_token_content(self):
        assert verify_token("user1:12345:abc") == "default_user"


class TestValidateUserToken:

    @pytest.mark.asyncio
    async def test_validate_returns_default_user(self):
        result = await validate_user_token()
        assert result == "default_user"
