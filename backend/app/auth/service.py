"""
DocuMind — Authentication Service (Fixed)
==========================================
Google OAuth token verification + lifetime query limit.

Auth strategy: Google OAuth only.
    The frontend sends the Google id_token (credential) from the
    Identity Services SDK on every API request as:
        Authorization: Bearer <google_id_token>

    The backend verifies this token against Google's public keys
    on every request. No separate JWT issued — no token storage
    complexity, no refresh logic, no expiry management beyond
    Google's own 1-hour token lifetime.

    Trade-off: one Google API call per request (cached by the
    google-auth library). For a portfolio system this is fine.
    For high-traffic production, issue your own short-lived JWT.

Query limit: 3 lifetime queries per account.
    Identical to InsightIQ. The atomic UPDATE pattern:

        UPDATE users
        SET total_queries = total_queries + 1,
            updated_at    = NOW()
        WHERE id            = $1
          AND is_active     = TRUE
          AND total_queries < query_limit
        RETURNING total_queries, query_limit

    If this returns no row, the limit is reached.
    If it returns a row, the request is permitted.
    One statement — no race condition possible.

Security:
    - Google id_token verified against Google's public keys (not
      decoded only — signature must be valid)
    - Audience claim validated against GOOGLE_CLIENT_ID
    - Failed verification raises AuthError with no internal detail
      (prevents oracle attacks on token structure)
    - User upserted by google_id — email/name changes handled
    - Inactive users rejected after limit check
"""

import logging
import uuid
from typing import Optional

import asyncpg
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.core.exceptions import DocuMindError

logger = logging.getLogger(__name__)


class AuthError(DocuMindError):
    """Raised for all authentication and authorisation failures."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


class QueryLimitExceeded(DocuMindError):
    """Raised when a user has used all their lifetime queries."""


# ── Google token verification ──────────────────────────────────────


def verify_google_token(id_token: str) -> dict:
    """
    Verify a Google id_token and return the claims.

    Verifies:
      - Token signature against Google's public keys
      - Audience matches our GOOGLE_CLIENT_ID
      - Token is not expired

    Raises AuthError with a generic message on any failure —
    deliberately vague to prevent oracle attacks.
    """
    try:
        claims = google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        logger.warning("Google token verification failed", extra={"error": str(exc)})
        raise AuthError("Invalid authentication token.") from exc

    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise AuthError("Token audience mismatch.")

    return claims


# ── User operations ────────────────────────────────────────────────


async def get_or_create_user(claims: dict) -> dict:
    """
    Upsert a user from Google OAuth claims.

    ON CONFLICT on google_id updates email/name/avatar so profile
    changes in Google are reflected on next sign-in.

    Returns the full user record.
    """
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, google_id, email, name, avatar_url)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (google_id) DO UPDATE
                SET email      = EXCLUDED.email,
                    name       = EXCLUDED.name,
                    avatar_url = EXCLUDED.avatar_url,
                    updated_at = NOW()
            RETURNING id, google_id, email, name, avatar_url,
                      total_queries, query_limit, is_active
            """,
            str(uuid.uuid4()),
            claims["sub"],
            claims.get("email", ""),
            claims.get("name"),
            claims.get("picture"),
        )
        return dict(row)
    finally:
        await conn.close()


async def get_user_by_google_id(google_id: str) -> Optional[dict]:
    """Fetch a user by their Google sub claim. Returns None if not found."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, email, name, avatar_url,
                   total_queries, query_limit, is_active
            FROM users WHERE google_id = $1
            """,
            google_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def check_and_increment_query_limit(user_id: str) -> dict:
    """
    Atomically check and increment the lifetime query counter.

    Single UPDATE statement — the check (total_queries < query_limit)
    and the increment happen in one operation. If no row is returned,
    the limit has been reached. No separate SELECT, no race condition.

    Returns:
        dict with total_queries and query_limit.

    Raises:
        QueryLimitExceeded: User has used all lifetime queries.
        AuthError:          User not found or inactive.
    """
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET total_queries = total_queries + 1,
                updated_at    = NOW()
            WHERE id            = $1
              AND is_active     = TRUE
              AND total_queries < query_limit
            RETURNING total_queries, query_limit
            """,
            user_id,
        )
    finally:
        await conn.close()

    if row is None:
        # Check whether the user exists at all (vs limit reached)
        user = await _get_user_by_id_minimal(user_id)
        if user is None or not user["is_active"]:
            raise AuthError("User account not found or inactive.", status_code=403)
        raise QueryLimitExceeded(
            f"You have used all {user['query_limit']} lifetime "
            "queries available on this account."
        )

    return dict(row)


async def _get_user_by_id_minimal(user_id: str) -> Optional[dict]:
    """Minimal fetch for limit-exceeded error disambiguation."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT id, is_active, query_limit FROM users WHERE id = $1",
            user_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()
