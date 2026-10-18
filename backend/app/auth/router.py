"""
DocuMind — Auth Router + FastAPI Dependency (Fixed)
=====================================================
Google OAuth only — no separate JWT issued.

The Google id_token from the Identity Services SDK is sent on
every request as Authorization: Bearer <id_token>.
The backend verifies it against Google's public keys each time.

This is simpler than issuing our own JWT:
  - No token storage on the client
  - No expiry management (Google handles it)
  - No refresh token flow
  - One less secret to manage (no JWT_SECRET_KEY)

Trade-off: Google public key lookup on every authenticated request
(cached by google-auth library, typically <5ms after first call).
Acceptable for a portfolio system.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.service import (
    AuthError,
    get_or_create_user,
    verify_google_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


# ── FastAPI dependency ─────────────────────────────────────────────


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> dict:
    """
    Validate the Google id_token from the Authorization header
    and return the authenticated user dict.

    Flow:
        1. Extract Bearer token from Authorization header
        2. Verify against Google's public keys
        3. Upsert user in Postgres (creates on first sign-in)
        4. Return user dict for downstream use

    Raises HTTP 401 if:
        - No Authorization header
        - Token scheme is not Bearer
        - Token is invalid, expired, or wrong audience
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = verify_google_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_or_create_user(claims)

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    return user


# Shorthand for dependency injection in route signatures
CurrentUser = Annotated[dict, Depends(get_current_user)]


# ── Request / Response models ──────────────────────────────────────


class GoogleAuthRequest(BaseModel):
    """
    Used by the frontend to exchange a Google credential for
    a user profile. The credential IS the id_token from the
    Identity Services SDK callback.
    """

    credential: str


# ── Routes ─────────────────────────────────────────────────────────


@router.post(
    "/auth/google",
    summary="Sign in with Google",
    status_code=status.HTTP_200_OK,
)
async def google_auth(body: GoogleAuthRequest) -> dict:
    """
    Verify a Google credential and return the user profile.
    Called once after the Google sign-in button is clicked.
    The frontend stores the Google credential and sends it as
    Authorization: Bearer on all subsequent requests.
    """
    try:
        claims = verify_google_token(body.credential)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    user = await get_or_create_user(claims)
    logger.info("User authenticated", extra={"user_id": user["id"]})

    return _safe_user(user)


@router.get(
    "/auth/me",
    summary="Get current user profile",
)
async def me(user: CurrentUser) -> dict:
    """
    Return the authenticated user's profile and query usage.
    Verifies the Google token on every call.
    """
    return _safe_user(user)


@router.post(
    "/auth/logout",
    summary="Sign out",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout() -> None:
    """
    Client-side logout — the frontend discards the Google credential.
    This endpoint exists for completeness and future server-side
    token revocation if needed.
    """
    return None


# ── Helpers ────────────────────────────────────────────────────────


def _safe_user(user: dict) -> dict:
    """
    Return only safe fields for API responses.
    Never exposes google_id (internal identifier) or is_active.
    queries_remaining is computed here so the frontend never
    needs to calculate it — single source of truth.
    """
    total = user.get("total_queries", 0)
    limit = user.get("query_limit", 3)
    remaining = max(0, limit - total)

    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "total_queries": total,
        "query_limit": limit,
        "queries_remaining": remaining,
    }
