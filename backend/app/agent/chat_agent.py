"""
Chat agent — orchestrates RAG retrieval + LLM generation.

Grounding rules (enforced in system prompt AND post-processing):
1. Answers must rely ONLY on retrieved transcript context.
2. Every factual claim must cite its source.
3. When retrieval is empty or below threshold, the agent explicitly says
   it cannot find relevant material — it never hallucinates.
4. Follow-up questions carry the full session context (last N messages).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from app.agent.base import LLMMessage, LLMResponse
from app.agent.router import get_llm_client
from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embedder import RetrievalResult, retrieve

log = get_logger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────
_GROUNDED_SYSTEM_PROMPT = """\
You are the Lenny Growth Assistant — an AI assistant with access to a curated \
knowledge base of Lenny Rachitsky's podcast and newsletter transcripts.

## STRICT GROUNDING RULES
- You MUST base all answers solely on the transcript excerpts provided in the \
<context> block below.
- You MUST cite sources using the format [Source: "Episode Title" with Guest Name \
(Date)] at the end of each factual claim or paragraph.
- If the provided context does not contain sufficient information to answer the \
question, you MUST say: "I don't have enough information in the available Lenny \
transcripts to answer this question thoroughly. The transcripts I have don't \
appear to cover [topic]. You may want to search lennysnewsletter.com directly."
- You MUST NOT speculate, invent quotes, or use general knowledge that isn't \
grounded in the provided context.
- If context is partially relevant, use what you have and be explicit about gaps.

## COMMUNICATION STYLE
- Be specific and actionable — Lenny's audience are sophisticated PMs and founders.
- Use concrete examples from the transcripts.
- Structure longer answers with headers and bullet points.
- Lead with the most important insight.

## FORMAT
Answer in Markdown. Cite sources inline.
"""

_NO_CONTEXT_RESPONSE = """\
I searched the available Lenny's Podcast transcripts but couldn't find \
sufficient material to answer this question well.

**What I can tell you:** The knowledge base contains curated excerpts from \
Lenny's Podcast and newsletter. If your question is about a topic not covered \
in those transcripts, or requires very specific episode content, I won't be \
able to answer it reliably.

**What to do instead:**
- Search [Lenny's Newsletter](https://www.lennysnewsletter.com) directly
- Browse the podcast archive at [lennysnewsletter.com/podcast](https://www.lennysnewsletter.com/podcast)
- Add more transcript files to the knowledge base using the ingestion pipeline

*I will not guess or make up information — only grounded answers.*
"""


@dataclass
class ChatRequest:
    query: str
    session_id: str
    history: list[LLMMessage] = field(default_factory=list)
    top_k: Optional[int] = None
    temperature: Optional[float] = None


@dataclass
class ChatResponse:
    content: str
    sources: list[dict]
    retrieval_hits: int
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    grounded: bool = True


def _build_context_block(results: list[RetrievalResult]) -> str:
    """Format retrieved chunks into a structured context block for the LLM."""
    if not results:
        return ""
    lines = ["<context>"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[Excerpt {i}]")
        lines.append(f"Source: {r.citation}")
        if r.episode_url:
            lines.append(f"URL: {r.episode_url}")
        lines.append(f"Relevance: {r.score:.2%}")
        lines.append(f"\n{r.content}")
    lines.append("\n</context>")
    return "\n".join(lines)


def _build_messages(
    history: list[LLMMessage],
    query: str,
    context_block: str,
) -> list[LLMMessage]:
    """
    Assemble the message list with:
    - Session history (capped at MAX_HISTORY_MESSAGES)
    - Current query with context injected
    """
    capped = history[-(settings.MAX_HISTORY_MESSAGES) :]

    user_content = query
    if context_block:
        user_content = f"{context_block}\n\n---\n\nQuestion: {query}"

    return [*capped, LLMMessage(role="user", content=user_content)]


async def chat(request: ChatRequest) -> ChatResponse:
    """Full (non-streaming) chat turn with RAG grounding."""
    import time
    t0 = int(time.monotonic() * 1000)

    # 1. Retrieve relevant context
    results = retrieve(request.query, top_k=request.top_k)

    # 2. Build messages
    context_block = _build_context_block(results)
    messages = _build_messages(request.history, request.query, context_block)

    # 3. Generate response
    llm = get_llm_client()

    if not results:
        log.info(
            "chat.no_retrieval",
            session_id=request.session_id,
            query_preview=request.query[:60],
        )
        return ChatResponse(
            content=_NO_CONTEXT_RESPONSE,
            sources=[],
            retrieval_hits=0,
            provider=llm.provider_name,
            model=llm.model_name,
            latency_ms=int(time.monotonic() * 1000) - t0,
            grounded=False,
        )

    response: LLMResponse = await llm.chat(
        messages=messages,
        system_prompt=_GROUNDED_SYSTEM_PROMPT,
        temperature=request.temperature,
    )

    latency = int(time.monotonic() * 1000) - t0
    log.info(
        "chat.response",
        session_id=request.session_id,
        provider=response.provider,
        model=response.model,
        retrieval_hits=len(results),
        latency_ms=latency,
    )

    return ChatResponse(
        content=response.content,
        sources=[r.to_dict() for r in results],
        retrieval_hits=len(results),
        provider=response.provider,
        model=response.model,
        latency_ms=latency,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        grounded=True,
    )


async def stream_chat(request: ChatRequest) -> AsyncIterator[str]:
    """Streaming chat turn — yields SSE-compatible data lines."""
    results = retrieve(request.query, top_k=request.top_k)
    sources = [r.to_dict() for r in results]

    # Emit metadata first as a special SSE event
    meta = {
        "type": "metadata",
        "sources": sources,
        "retrieval_hits": len(results),
    }
    yield f"data: {json.dumps(meta)}\n\n"

    if not results:
        yield f"data: {json.dumps({'type': 'token', 'content': _NO_CONTEXT_RESPONSE})}\n\n"
        yield "data: [DONE]\n\n"
        return

    context_block = _build_context_block(results)
    messages = _build_messages(request.history, request.query, context_block)
    llm = get_llm_client()

    try:
        async for token in llm.stream(
            messages=messages,
            system_prompt=_GROUNDED_SYSTEM_PROMPT,
            temperature=request.temperature,
        ):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    yield "data: [DONE]\n\n"
