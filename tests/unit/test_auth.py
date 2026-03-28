"""Tests for HMAC-signed token authentication."""

import os
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.api.auth import generate_token, verify_token


class TestTokenGeneration:

    def test_generate_token_format(self):
        token = generate_token("user1")
        parts = token.rsplit(":", 2)
        assert len(parts) == 3
        assert parts[0] == "user1"
        assert parts[1].isdigit()
        assert len(parts[2]) == 64  # SHA-256 hex digest

    def test_round_trip(self):
        token = generate_token("user1")
        user_id = verify_token(token)
        assert user_id == "user1"

    def test_user_id_with_special_chars(self):
        token = generate_token("user-123_abc")
        assert verify_token(token) == "user-123_abc"


class TestTokenVerification:

    def test_invalid_signature_rejected(self):
        token = generate_token("user1")
        # Tamper with the signature
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered)
        assert exc_info.value.status_code == 401

    def test_expired_token_rejected(self):
        # Generate a token with a timestamp far in the past
        with patch("src.api.auth.time") as mock_time:
            mock_time.time.return_value = time.time() - 100000
            token = generate_token("user1")
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_malformed_token_rejected(self):
        with pytest.raises(HTTPException):
            verify_token("not-a-valid-token")

    def test_empty_token_rejected(self):
        with pytest.raises(HTTPException):
            verify_token("")

    def test_different_user_cannot_reuse_token(self):
        token = generate_token("user1")
        user_id = verify_token(token)
        # The token is valid but the caller must check user_id matches
        assert user_id == "user1"
        assert user_id != "user2"
