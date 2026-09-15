"""
Vector store manager — ChromaDB-backed embedding and retrieval.

Uses sentence-transformers all-MiniLM-L6-v2 for local embeddings (no API key needed).
ChromaDB is persisted to CHROMA_PERSIST_DIR so embeddings survive restarts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import chromadb
    from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.exceptions import EmptyKnowledgeBaseError, RetrievalError
from app.core.logging import get_logger
from app.rag.chunker import TranscriptChunk

log = get_logger(__name__)

_embedding_model: Optional[object] = None
_chroma_client: Optional[object] = None
_collection = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        log.info("embedder.loading_model", model=settings.EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device=settings.EMBEDDING_DEVICE,
        )
        log.info("embedder.model_ready", model=settings.EMBEDDING_MODEL)
    return _embedding_model


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        import os
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_chroma_client()
        _collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def embed_chunks(chunks: list[TranscriptChunk], batch_size: int = 64) -> None:
    """
    Embed chunks and upsert them into ChromaDB.
    Uses upsert semantics so re-ingestion is idempotent.
    """
    if not chunks:
        log.warning("embedder.empty_chunk_list")
        return

    model = _get_embedding_model()
    collection = _get_collection()

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.content for c in batch]
        ids = [c.chunk_id for c in batch]
        metadatas = [c.to_metadata() for c in batch]

        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        log.info(
            "embedder.batch_upserted",
            batch=i // batch_size + 1,
            size=len(batch),
            total=len(chunks),
        )

    log.info("embedder.done", total_chunks=len(chunks))


@dataclass
class RetrievalResult:
    """A single retrieved chunk with similarity score and source metadata."""

    chunk_id: str
    content: str
    score: float               # Cosine similarity 0→1 (higher = more relevant)
    title: str
    guest: Optional[str]
    published_date: Optional[str]
    episode_url: Optional[str]
    citation: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": round(self.score, 4),
            "title": self.title,
            "guest": self.guest,
            "published_date": self.published_date,
            "episode_url": self.episode_url,
            "citation": self.citation,
        }


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    min_score: Optional[float] = None,
) -> list[RetrievalResult]:
    """
    Retrieve the most relevant transcript chunks for a query.

    Args:
        query: The user's question.
        top_k: Number of chunks to retrieve. Defaults to settings.RAG_TOP_K.
        min_score: Minimum similarity score threshold. Defaults to settings.RAG_MIN_SCORE.

    Returns:
        List of RetrievalResult ordered by descending relevance.
        Empty list if the knowledge base has no matching content.
    """
    k = top_k or settings.RAG_TOP_K
    threshold = min_score if min_score is not None else settings.RAG_MIN_SCORE

    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            log.warning("retriever.empty_index")
            return []

        model = _get_embedding_model()
        query_embedding = model.encode([query]).tolist()

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(k, count),
            include=["documents", "metadatas", "distances"],
        )

        retrieved: list[RetrievalResult] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            # ChromaDB cosine distance → similarity: 1 - distance
            score = 1.0 - float(dist)
            if score < threshold:
                continue
            retrieved.append(
                RetrievalResult(
                    chunk_id=meta.get("chunk_id", ""),
                    content=doc,
                    score=score,
                    title=meta.get("title", "Unknown Episode"),
                    guest=meta.get("guest") or None,
                    published_date=meta.get("published_date") or None,
                    episode_url=meta.get("episode_url") or None,
                    citation=meta.get("citation", meta.get("title", "Unknown")),
                )
            )

        log.info(
            "retriever.results",
            query_preview=query[:60],
            hits=len(retrieved),
            total_candidates=len(documents),
            threshold=threshold,
        )
        return retrieved

    except Exception as exc:
        log.error("retriever.error", error=str(exc))
        raise RetrievalError(f"Vector retrieval failed: {exc}") from exc


def get_index_stats() -> dict:
    """Return current index statistics for the /health endpoint."""
    try:
        collection = _get_collection()
        count = collection.count()
        return {"status": "healthy", "chunk_count": count, "collection": settings.CHROMA_COLLECTION}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}
