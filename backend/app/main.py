"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.database import create_tables

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup and shutdown."""
    configure_logging()
    log.info("app.starting", name=settings.APP_NAME, version=settings.APP_VERSION)

    # Create DB tables (idempotent)
    try:
        await create_tables()
        log.info("app.db_ready")
    except Exception as exc:
        log.error("app.db_startup_error", error=str(exc))
        # Don't crash — DB might be temporarily unavailable

    # Warm up embedding model in background asynchronously without blocking server startup
    import asyncio
    async def _async_warmup():
        try:
            from app.rag.embedder import _get_embedding_model
            await asyncio.to_thread(_get_embedding_model)
            log.info("app.embedder_ready")
        except Exception as exc:
            log.warning("app.embedder_warmup_failed", error=str(exc))

    asyncio.create_task(_async_warmup())

    log.info("app.ready", provider=settings.LLM_PROVIDER.value)
    yield

    log.info("app.shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Conversational AI assistant grounded in Lenny Rachitsky's "
        "podcast and newsletter transcripts."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
register_exception_handlers(app)

# Routers
from app.api import health, sessions, chat, artifacts  # noqa: E402

app.include_router(health.router)
app.include_router(sessions.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }
