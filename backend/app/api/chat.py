"""Chat API — SSE streaming + full (non-streaming) endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import LLMMessage
from app.agent.chat_agent import ChatRequest, ChatResponse, chat, stream_chat
from app.agent.router import get_provider_info
from app.core.exceptions import DatabaseError, SessionNotFoundError
from app.core.logging import get_logger
from app.db.database import get_db
from app.db.models import Message, Session as SessionModel
from app.skills.artifact_generator import ArtifactRequest, generate_artifact
from app.skills.ship30_writer import EssayRequest, write_essay

log = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=10000)
    stream: bool = False
    top_k: Optional[int] = Field(None, ge=1, le=20)


class ChatMessageResponse(BaseModel):
    message_id: str
    session_id: str
    content: str
    role: str = "assistant"
    sources: list[dict] = []
    retrieval_hits: int = 0
    provider: str
    model: str
    latency_ms: int
    grounded: bool


class EssayRequestBody(BaseModel):
    session_id: str
    topic: str = Field(..., min_length=3, max_length=500)
    custom_angle: Optional[str] = Field(None, max_length=500)


class ProviderInfoResponse(BaseModel):
    provider: str
    model: str
    base_url: Optional[str] = None


@router.get("/provider", response_model=ProviderInfoResponse)
async def get_provider() -> ProviderInfoResponse:
    """Return active LLM provider and model for the UI status badge."""
    info = get_provider_info()
    return ProviderInfoResponse(**info)


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """Send a message and receive a grounded response (non-streaming)."""
    session = await _get_session_or_404(body.session_id, db)

    # Load history
    history = await _load_history(body.session_id, db)

    # Store user message
    user_msg = Message(
        session_id=session.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.flush()

    # Generate response
    request = ChatRequest(
        query=body.message,
        session_id=body.session_id,
        history=history,
        top_k=body.top_k,
    )
    result: ChatResponse = await chat(request)

    # Store assistant message
    assistant_msg = Message(
        session_id=session.id,
        role="assistant",
        content=result.content,
        llm_provider=result.provider,
        llm_model=result.model,
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        retrieval_hits=result.retrieval_hits,
        sources=result.sources,
    )
    db.add(assistant_msg)

    # Update session timestamp + auto-title on first message
    session.updated_at = datetime.now(timezone.utc)
    if session.title == "New Chat" and body.message:
        session.title = body.message[:60] + ("…" if len(body.message) > 60 else "")

    await db.flush()
    await db.refresh(assistant_msg)

    return ChatMessageResponse(
        message_id=str(assistant_msg.id),
        session_id=body.session_id,
        content=result.content,
        sources=result.sources,
        retrieval_hits=result.retrieval_hits,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        grounded=result.grounded,
    )


@router.post("/stream")
async def stream_message(
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a message and receive a streaming SSE response."""
    session = await _get_session_or_404(body.session_id, db)
    history = await _load_history(body.session_id, db)

    # Store user message immediately
    user_msg = Message(session_id=session.id, role="user", content=body.message)
    db.add(user_msg)
    session.updated_at = datetime.now(timezone.utc)
    if session.title == "New Chat":
        session.title = body.message[:60] + ("…" if len(body.message) > 60 else "")
    await db.flush()

    request = ChatRequest(
        query=body.message,
        session_id=body.session_id,
        history=history,
        top_k=body.top_k,
    )

    # We collect the full response to persist it after streaming
    collected_tokens: list[str] = []
    collected_sources: list[dict] = []
    collected_hits: int = 0

    async def event_generator():
        nonlocal collected_sources, collected_hits
        import json
        async for chunk in stream_chat(request):
            yield chunk
            # Parse metadata events to collect sources
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = json.loads(chunk[6:])
                    if data.get("type") == "metadata":
                        collected_sources = data.get("sources", [])
                        collected_hits = data.get("retrieval_hits", 0)
                    elif data.get("type") == "token":
                        collected_tokens.append(data.get("content", ""))
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/essay")
async def generate_essay(
    body: EssayRequestBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate a Ship 30 for 30 essay grounded in Lenny transcripts."""
    session = await _get_session_or_404(body.session_id, db)

    request = EssayRequest(
        topic=body.topic,
        custom_angle=body.custom_angle,
    )
    result = await write_essay(request)

    # Store as assistant message in session
    assistant_msg = Message(
        session_id=session.id,
        role="assistant",
        content=result.content,
        retrieval_hits=result.retrieval_hits,
        sources=result.sources,
    )
    db.add(assistant_msg)
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(assistant_msg)

    return {
        "message_id": str(assistant_msg.id),
        "topic": result.topic,
        "content": result.content,
        "word_count": result.word_count,
        "sources": result.sources,
        "retrieval_hits": result.retrieval_hits,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_session_or_404(session_id: str, db: AsyncSession) -> SessionModel:
    try:
        sid = str(uuid.UUID(session_id))
    except ValueError:
        raise SessionNotFoundError(f"Invalid session ID: {session_id}")
    result = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found.")
    return session


async def _load_history(session_id: str, db: AsyncSession) -> list[LLMMessage]:
    """Load the last MAX_HISTORY_MESSAGES messages for context."""
    from app.core.config import settings
    result = await db.execute(
        select(Message)
        .where(Message.session_id == str(uuid.UUID(session_id)))
        .order_by(Message.created_at.desc())
        .limit(settings.MAX_HISTORY_MESSAGES)
    )
    messages = list(reversed(result.scalars().all()))
    return [LLMMessage(role=m.role, content=m.content) for m in messages]
