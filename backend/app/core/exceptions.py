"""
Custom exception hierarchy and FastAPI exception handlers.
All errors return a consistent JSON envelope:
  { "error": { "code": str, "message": str, "details": any } }
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# ── Base ──────────────────────────────────────────────────────────────────────

class AppError(Exception):
    """Base class for all application-level errors."""

    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self, message: str, details: Optional[Any] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        body: dict = {"code": self.error_code, "message": self.message}
        if self.details is not None:
            body["details"] = self.details
        return {"error": body}


# ── LLM ───────────────────────────────────────────────────────────────────────

class LLMUnavailableError(AppError):
    http_status = 503
    error_code = "LLM_UNAVAILABLE"


class LLMTimeoutError(AppError):
    http_status = 504
    error_code = "LLM_TIMEOUT"


class LLMAuthError(AppError):
    http_status = 401
    error_code = "LLM_AUTH_ERROR"


class LLMProviderError(AppError):
    http_status = 502
    error_code = "LLM_PROVIDER_ERROR"


# ── RAG ───────────────────────────────────────────────────────────────────────

class RetrievalError(AppError):
    http_status = 500
    error_code = "RETRIEVAL_ERROR"


class EmptyKnowledgeBaseError(AppError):
    http_status = 422
    error_code = "EMPTY_KNOWLEDGE_BASE"


# ── Database ──────────────────────────────────────────────────────────────────

class DatabaseError(AppError):
    http_status = 500
    error_code = "DATABASE_ERROR"


class SessionNotFoundError(AppError):
    http_status = 404
    error_code = "SESSION_NOT_FOUND"


class ArtifactNotFoundError(AppError):
    http_status = 404
    error_code = "ARTIFACT_NOT_FOUND"


# ── Artifacts ─────────────────────────────────────────────────────────────────

class ArtifactRenderError(AppError):
    http_status = 422
    error_code = "ARTIFACT_RENDER_ERROR"


# ── FastAPI integration ───────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak tracebacks to clients in production
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                }
            },
        )
