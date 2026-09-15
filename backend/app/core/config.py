"""
Application configuration — reads from environment variables.
Uses pydantic-settings so every value is typed and validated at startup.
"""
from __future__ import annotations

import enum
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "Lenny Growth Assistant"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql://lenny:lenny@localhost:5432/lenny_db",
        description="Full PostgreSQL connection URL",
    )

    # ── Vector Store ──────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = Field(
        default="./data/embeddings",
        description="Directory ChromaDB persists its data to",
    )
    CHROMA_COLLECTION: str = "lenny_transcripts"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    LLM_PROVIDER: LLMProvider = LLMProvider.OLLAMA
    LLM_TEMPERATURE: float = Field(default=0.3, ge=0.0, le=2.0)
    LLM_MAX_TOKENS: int = Field(default=4096, ge=64)

    # ── Anthropic ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"

    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    OLLAMA_TIMEOUT: int = 120  # seconds

    # ── Embeddings ────────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"

    # ── RAG ───────────────────────────────────────────────────────────────────
    RAG_TOP_K: int = Field(default=5, ge=1, le=20)
    RAG_CHUNK_SIZE: int = Field(default=512, ge=128)
    RAG_CHUNK_OVERLAP: int = Field(default=64, ge=0)
    RAG_MIN_SCORE: float = Field(default=0.3, ge=0.0, le=1.0)

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── Session ───────────────────────────────────────────────────────────────
    MAX_HISTORY_MESSAGES: int = 20  # per-session context window

    @field_validator("LLM_PROVIDER", mode="before")
    @classmethod
    def normalise_provider(cls, v: str) -> str:
        return str(v).lower()

    @model_validator(mode="after")
    def validate_provider_keys(self) -> "Settings":
        if self.LLM_PROVIDER == LLMProvider.ANTHROPIC and not self.ANTHROPIC_API_KEY:
            import warnings
            warnings.warn(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "Requests will fail until the key is provided.",
                stacklevel=2,
            )
        if self.LLM_PROVIDER == LLMProvider.OPENAI and not self.OPENAI_API_KEY:
            import warnings
            warnings.warn(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Requests will fail until the key is provided.",
                stacklevel=2,
            )
        return self


# Singleton — import `settings` everywhere.
settings = Settings()
