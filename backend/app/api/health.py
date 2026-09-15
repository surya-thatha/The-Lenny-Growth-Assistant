"""Health check endpoint — checks all system components."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.logging import get_logger
from app.db.database import check_db_health
from app.rag.embedder import get_index_stats

log = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Comprehensive health check for all system components.
    Returns per-component status so operators can quickly identify failures.
    """
    from app.agent.router import get_llm_client, get_provider_info
    from app.core.config import settings

    # Check database
    db_health = await check_db_health()

    # Check vector store
    index_health = get_index_stats()

    # Check LLM provider
    llm_health: dict = {"status": "unknown"}
    provider_info = get_provider_info()
    try:
        llm = get_llm_client()
        is_healthy = await llm.health_check()
        llm_health = {
            "status": "healthy" if is_healthy else "unhealthy",
            "provider": provider_info["provider"],
            "model": provider_info["model"],
        }
        if not is_healthy:
            llm_health["note"] = (
                "LLM provider is unreachable. "
                f"If using Ollama, run: brew services start ollama && ollama pull {settings.OLLAMA_MODEL}"
            )
    except Exception as exc:
        llm_health = {
            "status": "unhealthy",
            "provider": provider_info["provider"],
            "error": str(exc),
        }

    overall = "healthy"
    if db_health["status"] != "healthy":
        overall = "degraded"
    if index_health["status"] != "healthy":
        overall = "degraded"

    status_code = 200 if overall == "healthy" else 207

    return {
        "status": overall,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "components": {
            "database": db_health,
            "vector_store": index_health,
            "llm": llm_health,
        },
    }


@router.get("/health/ready")
async def readiness() -> dict:
    """Kubernetes-style readiness probe — DB must be up."""
    db = await check_db_health()
    if db["status"] != "healthy":
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"ready": True}


@router.get("/health/live")
async def liveness() -> dict:
    """Kubernetes-style liveness probe — always returns 200 if process is up."""
    return {"alive": True}
