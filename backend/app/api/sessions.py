"""Sessions API router."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseError, SessionNotFoundError
from app.core.logging import get_logger
from app.db.database import get_db
from app.db.models import Session as SessionModel, Message

log = get_logger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)


class SessionResponse(BaseModel):
    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    message_count: int = 0

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    latency_ms: Optional[int] = None
    sources: Optional[list] = None
    retrieval_hits: Optional[int] = None


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Create a new independent chat session."""
    try:
        session = SessionModel(title=body.title or "New Chat")
        db.add(session)
        await db.flush()
        await db.refresh(session)
        log.info("session.created", session_id=str(session.id))
        return _session_to_response(session, message_count=0)
    except Exception as exc:
        log.error("session.create_error", error=str(exc))
        raise DatabaseError(f"Failed to create session: {exc}") from exc


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all active sessions, newest first."""
    try:
        result = await db.execute(
            select(SessionModel)
            .where(SessionModel.is_active == True)
            .order_by(SessionModel.updated_at.desc())
            .limit(limit)
        )
        sessions = result.scalars().all()

        responses = []
        for s in sessions:
            count_result = await db.execute(
                select(Message).where(Message.session_id == s.id)
            )
            count = len(count_result.scalars().all())
            responses.append(_session_to_response(s, count))
        return responses
    except Exception as exc:
        raise DatabaseError(f"Failed to list sessions: {exc}") from exc


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    """Get a session by ID."""
    session = await _get_session_or_404(session_id, db)
    count_result = await db.execute(
        select(Message).where(Message.session_id == session.id)
    )
    count = len(count_result.scalars().all())
    return _session_to_response(session, count)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """Get all messages for a session."""
    await _get_session_or_404(session_id, db)
    result = await db.execute(
        select(Message)
        .where(Message.session_id == str(uuid.UUID(session_id)))
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [_message_to_response(m) for m in messages]


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Update session title."""
    session = await _get_session_or_404(session_id, db)
    if body.title:
        session.title = body.title
        await db.flush()
        await db.refresh(session)
    return _session_to_response(session)


@router.delete("/{session_id}", status_code=204, response_class=Response)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    """Soft-delete a session (marks as inactive, preserves data)."""
    session = await _get_session_or_404(session_id, db)
    session.is_active = False
    await db.flush()
    log.info("session.deleted", session_id=session_id)
    return Response(status_code=204)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_session_or_404(session_id: str, db: AsyncSession) -> SessionModel:
    try:
        sid = str(uuid.UUID(session_id))
    except ValueError:
        raise SessionNotFoundError(f"Invalid session ID format: {session_id}")
    result = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found.")
    return session


def _session_to_response(session: SessionModel, message_count: int = 0) -> SessionResponse:
    return SessionResponse(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        message_count=message_count,
    )


def _message_to_response(m: Message) -> MessageResponse:
    return MessageResponse(
        id=str(m.id),
        session_id=str(m.session_id),
        role=m.role,
        content=m.content,
        created_at=m.created_at.isoformat(),
        llm_provider=m.llm_provider,
        llm_model=m.llm_model,
        latency_ms=m.latency_ms,
        sources=m.sources,
        retrieval_hits=m.retrieval_hits,
    )
