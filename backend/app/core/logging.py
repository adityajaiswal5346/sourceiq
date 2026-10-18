"""
DocuMind — Logging configuration
=================================
Centralised logging setup for the API and RAG pipelines.
"""

import logging
import sys


def configure_logging(level: str | None = None) -> None:
    """Configure root logger from settings.LOG_LEVEL (or explicit level)."""
    from app.core.config import settings

    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
