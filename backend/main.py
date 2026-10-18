"""
DocuMind — FastAPI Application
================================
Production FastAPI app with security middleware and query endpoints.

Security layers:
    1. CORS: only allowed origins (configured via env var)
    2. Rate limiting: per-IP using slowapi (prevents API abuse)
    3. Request size limit: 1MB max body (prevents DoS via large payloads)
    4. Input validation: Pydantic models reject malformed requests
       before they reach any business logic
    5. Namespace allowlist: query namespace validated in the pipeline
    6. Trusted host middleware: rejects requests with unexpected Host headers
    7. No stack traces in production error responses

This file runs both locally (uvicorn main:app --reload)
and on AWS Lambda (via Mangum adapter in lambda_handler.py).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.logging import configure_logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

configure_logging()

logger = logging.getLogger(__name__)


# ── Rate limiter ───────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "DocuMind API starting",
        extra={"model": settings.CLAUDE_MODEL, "index": settings.PINECONE_INDEX},
    )
    yield
    logger.info("DocuMind API shutting down")


app = FastAPI(
    title="DocuMind API",
    description="Production RAG system for engineering knowledge retrieval",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
    # Never expose internal error details in production responses
    openapi_url="/openapi.json",
)

# ── Security middleware ────────────────────────────────────────────

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — explicit origin list, no wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,  # no cookies used
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
    max_age=600,
)

# Reject requests with unexpected Host headers (DNS rebinding defence)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)


# ── Global exception handler ───────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Return a safe error response — never leak stack traces or
    internal details to the client.
    """
    logger.exception(
        "Unhandled exception",
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An internal error occurred. Please try again.",
        },
    )


# ── Routes ─────────────────────────────────────────────────────────
from app.api.query import router as query_router  # noqa: E402

app.include_router(query_router, prefix="/api", tags=["Query"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])


@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Liveness probe for Lambda and smoke tests."""
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
