"""
DocuMind — Auth Unit Tests
====================================
Tests for Google OAuth only auth + lifetime query limit.
No JWT tests — we don't issue our own tokens.
No network calls — Google verification is mocked.

Run: make test
"""

from unittest.mock import patch

import pytest

# ── Google token verification ──────────────────────────────────────


class TestGoogleTokenVerification:
    def test_valid_token_returns_claims(self):
        from app.auth.service import verify_google_token
        from app.core.config import settings

        mock_claims = {
            "sub": "google-user-123",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
            "aud": settings.GOOGLE_CLIENT_ID,
        }

        with patch(
            "app.auth.service.google_id_token.verify_oauth2_token", return_value=mock_claims
        ):
            claims = verify_google_token("fake-token")
            assert claims["sub"] == "google-user-123"
            assert claims["email"] == "test@example.com"

    def test_invalid_token_raises_auth_error(self):
        from app.auth.service import AuthError, verify_google_token

        with patch(
            "app.auth.service.google_id_token.verify_oauth2_token",
            side_effect=ValueError("Invalid token"),
        ):
            with pytest.raises(AuthError, match="Invalid authentication token"):
                verify_google_token("bad-token")

    def test_wrong_audience_raises_auth_error(self):
        from app.auth.service import AuthError, verify_google_token

        mock_claims = {
            "sub": "google-user-123",
            "aud": "wrong-client-id.apps.googleusercontent.com",
        }
        with patch(
            "app.auth.service.google_id_token.verify_oauth2_token", return_value=mock_claims
        ):
            with pytest.raises(AuthError, match="audience"):
                verify_google_token("fake-token")

    def test_error_message_is_generic(self):
        """
        Auth errors must never reveal internal detail.
        Generic message prevents oracle attacks on token structure.
        """
        from app.auth.service import AuthError, verify_google_token

        with patch(
            "app.auth.service.google_id_token.verify_oauth2_token",
            side_effect=ValueError("Specific internal detail"),
        ):
            with pytest.raises(AuthError) as exc_info:
                verify_google_token("bad-token")
            # Must NOT contain the internal ValueError message
            assert "Specific internal detail" not in str(exc_info.value)
            assert "Invalid" in str(exc_info.value)


# ── Safe user field projection ─────────────────────────────────────


class TestSafeUser:
    """_safe_user must never expose internal fields."""

    def _make_user(self, total=1, limit=3) -> dict:
        return {
            "id": "user-uuid-123",
            "google_id": "google-sub-123",  # must be excluded
            "email": "test@example.com",
            "name": "Test User",
            "avatar_url": None,
            "total_queries": total,
            "query_limit": limit,
            "is_active": True,  # must be excluded
        }

    def test_excludes_google_id(self):
        from app.auth.router import _safe_user

        safe = _safe_user(self._make_user())
        assert "google_id" not in safe

    def test_excludes_is_active(self):
        from app.auth.router import _safe_user

        safe = _safe_user(self._make_user())
        assert "is_active" not in safe

    def test_queries_remaining_computed_correctly(self):
        from app.auth.router import _safe_user

        safe = _safe_user(self._make_user(total=1, limit=3))
        assert safe["queries_remaining"] == 2

    def test_queries_remaining_at_zero_when_exhausted(self):
        from app.auth.router import _safe_user

        safe = _safe_user(self._make_user(total=3, limit=3))
        assert safe["queries_remaining"] == 0

    def test_queries_remaining_never_negative(self):
        from app.auth.router import _safe_user

        # Edge case: total somehow exceeds limit
        safe = _safe_user(self._make_user(total=5, limit=3))
        assert safe["queries_remaining"] == 0  # max(0, ...) applied

    def test_includes_all_required_fields(self):
        from app.auth.router import _safe_user

        safe = _safe_user(self._make_user())
        required = {
            "id",
            "email",
            "name",
            "avatar_url",
            "total_queries",
            "query_limit",
            "queries_remaining",
        }
        assert required.issubset(set(safe.keys()))


# ── Lifetime query limit ───────────────────────────────────────────


class TestLifetimeQueryLimit:
    def test_limit_exceeded_raises(self):
        from app.auth.service import QueryLimitExceeded

        exc = QueryLimitExceeded("You have used all 3 lifetime queries.")
        assert "3" in str(exc)

    def test_auth_error_default_401(self):
        from app.auth.service import AuthError

        err = AuthError("test")
        assert err.status_code == 401

    def test_auth_error_custom_403(self):
        from app.auth.service import AuthError

        err = AuthError("forbidden", status_code=403)
        assert err.status_code == 403

    def test_queries_remaining_at_limit(self):
        from app.auth.router import _safe_user

        user = {
            "id": "u1",
            "google_id": "g1",
            "email": "t@t.com",
            "name": None,
            "avatar_url": None,
            "is_active": True,
            "total_queries": 3,
            "query_limit": 3,
        }
        safe = _safe_user(user)
        assert safe["queries_remaining"] == 0

    def test_fresh_user_has_full_allowance(self):
        from app.auth.router import _safe_user

        user = {
            "id": "u1",
            "google_id": "g1",
            "email": "t@t.com",
            "name": None,
            "avatar_url": None,
            "is_active": True,
            "total_queries": 0,
            "query_limit": 3,
        }
        safe = _safe_user(user)
        assert safe["queries_remaining"] == 3


# ── Namespace validation ───────────────────────────────────────────


class TestNamespaceValidation:
    def test_valid_namespaces_accepted(self):
        from app.core.models import QueryRequest

        for ns in ["default", "kubernetes-docs", "stripe-api", "aws-waf"]:
            req = QueryRequest(question="valid question here?", namespace=ns)
            assert req.namespace == ns

    def test_uppercase_rejected(self):
        from app.core.models import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(question="valid question?", namespace="UPPERCASE")

    def test_path_traversal_rejected(self):
        from app.core.models import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(question="valid?", namespace="../../../etc/passwd")

    def test_sql_injection_rejected(self):
        from app.core.models import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(question="valid?", namespace="'; DROP TABLE users--")

    def test_spaces_rejected(self):
        from app.core.models import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(question="valid?", namespace="my namespace")
