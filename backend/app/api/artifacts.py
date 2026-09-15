"""Artifacts API — generate, store, and retrieve Markdown/HTML artifacts."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ArtifactNotFoundError, DatabaseError
from app.core.logging import get_logger
from app.db.database import get_db
from app.db.models import Artifact, Session as SessionModel
from app.skills.artifact_generator import ArtifactRequest, generate_artifact

log = get_logger(__name__)
router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class GenerateArtifactRequest(BaseModel):
    session_id: str
    artifact_type: str = Field(..., pattern="^(markdown|html)$")
    description: str = Field(..., min_length=5, max_length=2000)
    conversation_context: str = Field("", max_length=5000)


class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    title: str
    artifact_type: str
    content: str
    sanitized_content: Optional[str] = None
    security_notes: str
    created_at: str


@router.post("", response_model=ArtifactResponse, status_code=201)
async def create_artifact(
    body: GenerateArtifactRequest,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    """Generate and store a Markdown or HTML artifact."""
    # Validate session exists
    try:
        sid = str(uuid.UUID(body.session_id))
    except ValueError:
        raise ArtifactNotFoundError(f"Invalid session ID: {body.session_id}")
    result = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    if not result.scalar_one_or_none():
        raise ArtifactNotFoundError(f"Session {body.session_id} not found.")

    # Generate artifact
    artifact_result = await generate_artifact(
        ArtifactRequest(
            artifact_type=body.artifact_type,
            conversation_context=body.conversation_context,
            description=body.description,
        )
    )

    # Persist
    artifact = Artifact(
        session_id=sid,
        title=artifact_result.title,
        artifact_type=artifact_result.artifact_type,
        content=artifact_result.raw_content,
        sanitized_content=artifact_result.sanitized_content,
    )
    db.add(artifact)
    await db.flush()
    await db.refresh(artifact)

    log.info(
        "artifact.stored",
        artifact_id=str(artifact.id),
        artifact_type=artifact.artifact_type,
        session_id=body.session_id,
    )

    return _artifact_to_response(artifact, artifact_result.security_notes)


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    """Retrieve an artifact by ID."""
    try:
        aid = str(uuid.UUID(artifact_id))
    except ValueError:
        raise ArtifactNotFoundError(f"Invalid artifact ID: {artifact_id}")

    result = await db.execute(select(Artifact).where(Artifact.id == aid))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise ArtifactNotFoundError(f"Artifact {artifact_id} not found.")

    return _artifact_to_response(artifact)


@router.get("/session/{session_id}", response_model=list[ArtifactResponse])
async def list_session_artifacts(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ArtifactResponse]:
    """List all artifacts for a session."""
    try:
        sid = str(uuid.UUID(session_id))
    except ValueError:
        raise ArtifactNotFoundError(f"Invalid session ID: {session_id}")

    result = await db.execute(
        select(Artifact)
        .where(Artifact.session_id == sid)
        .order_by(Artifact.created_at.desc())
    )
    artifacts = result.scalars().all()
    return [_artifact_to_response(a) for a in artifacts]


def _artifact_to_response(artifact: Artifact, security_notes: str = "") -> ArtifactResponse:
    notes = security_notes
    if not notes:
        if artifact.artifact_type == "html":
            notes = (
                "HTML artifact sanitized with bleach. "
                "Served in sandboxed iframe (sandbox='allow-scripts')."
            )
        else:
            notes = "Markdown — no sanitization required."

    return ArtifactResponse(
        id=str(artifact.id),
        session_id=str(artifact.session_id),
        title=artifact.title,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        sanitized_content=artifact.sanitized_content,
        security_notes=notes,
        created_at=artifact.created_at.isoformat(),
    )
