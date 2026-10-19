"""
DocuMind — AWS Lambda Handler
================================
Mangum wraps the FastAPI app so it runs as a Lambda function.
API Gateway sends events → Mangum converts to ASGI → FastAPI handles.

This file is the Lambda entry point: handler = lambda_handler.handler

Mangum is a 3-line adapter — the rest of the codebase is identical
to the local uvicorn server. No Lambda-specific code elsewhere.

Lifespan note:
    Lambda containers are reused across invocations (warm starts).
    FastAPI's lifespan context runs once per container start.
    On cold starts this adds ~500ms. Subsequent invocations reuse
    the warm container and skip lifespan initialisation.
"""

import os

# pyrefly: ignore[missing-import]
from app.main import app
from mangum import Mangum

# HTTP API URLs include the stage: .../prod/health
# FastAPI routes are /health, /api/... — strip the stage prefix for Mangum.
_stage = os.environ.get("API_STAGE", "").strip("/")
_api_base = f"/{_stage}" if _stage else ""

handler = Mangum(app, lifespan="auto", api_gateway_base_path=_api_base)
