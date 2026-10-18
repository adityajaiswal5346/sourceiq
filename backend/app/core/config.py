"""
DocuMind — Application Configuration
======================================
Centralised settings loaded from environment.
Pydantic validates every value at startup — a missing API key
raises a clear ValidationError before any pipeline runs.

All RAG tuning parameters (chunk size, alpha, top-k) are env vars
so they can be adjusted per document collection without code changes.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → repo root is three levels up from backend/
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    # ── LLM ───────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = Field(..., description="Anthropic API key")
    CLAUDE_MODEL: str = Field(default="claude-sonnet-4-5")

    # ── Embeddings ────────────────────────────────────────────
    VOYAGE_API_KEY: str = Field(..., description="Voyage AI API key")
    VOYAGE_MODEL: str = Field(default="voyage-2")
    VOYAGE_DIMS: int = Field(default=1024, description="Must match Pinecone index dimensions")

    # ── Vector DB ─────────────────────────────────────────────
    PINECONE_API_KEY: str = Field(..., description="Pinecone API key")
    PINECONE_INDEX: str = Field(default="documind")

    # ── Reranking ─────────────────────────────────────────────
    COHERE_API_KEY: str = Field(..., description="Cohere API key")
    COHERE_MODEL: str = Field(default="rerank-english-v3.0")

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = Field(..., description="Neon Postgres connection string")

    # ── AWS ───────────────────────────────────────────────────
    AWS_REGION: str = Field(default="us-east-1")
    S3_BUCKET: str = Field(default="documind-docs")

    # ── RAG tuning ────────────────────────────────────────────
    CHUNK_SIZE: int = Field(default=800, description="Tokens per chunk")
    CHUNK_OVERLAP: int = Field(default=100, description="Token overlap between chunks")
    TOP_K_RETRIEVAL: int = Field(default=10, description="Candidates from Pinecone")
    TOP_K_RERANK: int = Field(default=5, description="Final chunks passed to Claude")
    HYBRID_ALPHA: float = Field(default=0.7, description="0=keyword only, 1=semantic only")

    # ── App ───────────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")

    # ── Security (FastAPI CORS + trusted hosts) ───────────────
    # Comma-separated in .env — pydantic-settings cannot JSON-decode list fields
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173,http://localhost:3000",
    )
    TRUSTED_HOSTS: str = Field(
        default="localhost,127.0.0.1,testserver",
    )

    # ── Auth ───────────────────────────────────────────────────
    # Auth
    GOOGLE_CLIENT_ID: str = Field(..., description="Google OAuth client ID")

    # ── Langfuse (observability) ──────────────────────────────
    LANGFUSE_SECRET_KEY: str = Field(default="", description="Langfuse secret key")
    LANGFUSE_PUBLIC_KEY: str = Field(default="", description="Langfuse public key")
    LANGFUSE_BASE_URL: str = Field(default="https://cloud.langfuse.com")

    # ── Guardrails ────────────────────────────────────────────
    CONFIDENCE_THRESHOLD: float = Field(
        default=0.6, description="Min rerank score before generation"
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def fix_db_scheme(cls, v: str) -> str:
        return v.replace("postgres://", "postgresql://", 1)

    @field_validator("GOOGLE_CLIENT_ID")
    @classmethod
    def strip_client_id(cls, v: str) -> str:
        # Strip stray whitespace/newline (e.g. a secret set via `echo`).
        # A trailing "\n" would break the token audience check.
        return v.strip()

    @field_validator("HYBRID_ALPHA")
    @classmethod
    def validate_alpha(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("HYBRID_ALPHA must be between 0.0 and 1.0")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trusted_hosts(self) -> list[str]:
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — .env parsed once per process."""
    return Settings()


settings: Settings = get_settings()
