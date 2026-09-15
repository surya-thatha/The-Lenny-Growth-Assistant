"""
Semantic chunker — splits TranscriptDocuments into overlapping chunks
suitable for embedding and retrieval.

Design decisions:
- Chunks at sentence boundaries when possible (not mid-sentence).
- 512-token target size with 64-token overlap for continuity.
- Every chunk carries full source provenance (title, guest, date, url, chunk_id).
- Token counting uses a simple word-based approximation (fast, no tokenizer needed).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.ingester import TranscriptDocument

log = get_logger(__name__)

# Rough word-to-token ratio (conservative for English prose)
_WORDS_PER_TOKEN = 0.75


def _word_count(text: str) -> int:
    return len(text.split())


def _token_estimate(text: str) -> int:
    return int(_word_count(text) / _WORDS_PER_TOKEN)


def _split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation followed by whitespace."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


@dataclass
class TranscriptChunk:
    """A single chunk ready for embedding and retrieval."""

    chunk_id: str               # Unique ID: "{source_hash}_{chunk_index}"
    content: str                # The actual text to embed
    source_file: str
    title: str
    guest: Optional[str]
    published_date: Optional[str]
    episode_url: Optional[str]
    chunk_index: int
    total_chunks: int

    @property
    def citation(self) -> str:
        """Human-readable citation string."""
        parts = [f'"{self.title}"']
        if self.guest:
            parts.append(f"with {self.guest}")
        if self.published_date:
            parts.append(f"({self.published_date})")
        return " ".join(parts)

    def to_metadata(self) -> dict:
        """Serialisable dict for ChromaDB metadata."""
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "title": self.title,
            "guest": self.guest or "",
            "published_date": self.published_date or "",
            "episode_url": self.episode_url or "",
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "citation": self.citation,
        }


def chunk_document(
    doc: TranscriptDocument,
    chunk_size_tokens: Optional[int] = None,
    overlap_tokens: Optional[int] = None,
) -> list[TranscriptChunk]:
    """
    Split a TranscriptDocument into overlapping chunks.

    Args:
        doc: The document to chunk.
        chunk_size_tokens: Target chunk size in tokens. Defaults to settings.RAG_CHUNK_SIZE.
        overlap_tokens: Overlap between consecutive chunks. Defaults to settings.RAG_CHUNK_OVERLAP.

    Returns:
        List of TranscriptChunk objects with source metadata attached.
    """
    chunk_size = chunk_size_tokens or settings.RAG_CHUNK_SIZE
    overlap = overlap_tokens or settings.RAG_CHUNK_OVERLAP

    sentences = _split_sentences(doc.content)
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = _token_estimate(sentence)
        if current_tokens + sent_tokens > chunk_size and current:
            chunks.append(" ".join(current))
            # Overlap: keep the last N tokens worth of sentences
            overlap_sents: list[str] = []
            overlap_t = 0
            for s in reversed(current):
                t = _token_estimate(s)
                if overlap_t + t > overlap:
                    break
                overlap_sents.insert(0, s)
                overlap_t += t
            current = overlap_sents
            current_tokens = overlap_t
        current.append(sentence)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))

    # Build chunk objects with provenance
    total = len(chunks)
    result: list[TranscriptChunk] = []
    source_hash = doc.content_hash[:8]

    for i, text in enumerate(chunks):
        if len(text.strip()) < 50:
            continue
        result.append(
            TranscriptChunk(
                chunk_id=f"{source_hash}_{i:04d}",
                content=text,
                source_file=doc.source_file,
                title=doc.title,
                guest=doc.guest,
                published_date=doc.published_date,
                episode_url=doc.episode_url,
                chunk_index=i,
                total_chunks=total,
            )
        )

    log.debug(
        "chunker.document",
        title=doc.title,
        total_chunks=len(result),
        avg_tokens=sum(_token_estimate(c.content) for c in result) // max(len(result), 1),
    )
    return result


def chunk_documents(docs: list[TranscriptDocument]) -> list[TranscriptChunk]:
    """Chunk all documents and return a flat list."""
    all_chunks: list[TranscriptChunk] = []
    for doc in docs:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)
    log.info("chunker.summary", total_docs=len(docs), total_chunks=len(all_chunks))
    return all_chunks
