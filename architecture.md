# Architecture Document — Lenny Growth Assistant

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                   User's Browser                             │
│   React + Vite SPA  (SessionList | Chat | ArtifactViewer)   │
└───────────────────┬──────────────────────────────────────────┘
                    │ HTTP/SSE (REST + Server-Sent Events)
┌───────────────────▼──────────────────────────────────────────┐
│                  FastAPI Backend (:8000)                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │   API Layer (routers)                                  │  │
│  │   /api/sessions  /api/chat  /api/artifacts  /health    │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│  ┌───────────────────────▼──────────────────────────────────┐ │
│  │   Agent Layer                                            │ │
│  │   BaseLLM (abstract)                                     │ │
│  │   ├── AnthropicLLM  (claude-3-5-sonnet-20241022)        │ │
│  │   ├── OllamaLLM     (llama3.2:3b, local)                │ │
│  │   └── OpenAILLM     (gpt-4o)                            │ │
│  │   router.py → get_llm_client() [single branch point]    │ │
│  └──────────────────────┬───────────────────────────────────┘ │
│  ┌───────────────────────▼──────────────────────────────────┐ │
│  │   RAG Pipeline                                           │ │
│  │   ingester → chunker → embedder (MiniLM-L6-v2)          │ │
│  │   retriever → RetrievalResult[] (with provenance)        │ │
│  └──────────────────────┬───────────────────────────────────┘ │
│  ┌───────────────────────▼──────────────────────────────────┐ │
│  │   Skills                                                 │ │
│  │   ship30_writer.py  artifact_generator.py (+ bleach)     │ │
│  └──────────────────────────────────────────────────────────┘ │
└──┬──────────────────────────┬───────────────────────────────┘
   │                          │
┌──▼──────────────┐   ┌───────▼──────────────┐
│   PostgreSQL    │   │   ChromaDB           │
│   :5432         │   │   (local file store) │
│   sessions      │   │   lenny_transcripts  │
│   messages      │   │   (sentence embed.)  │
│   artifacts     │   └──────────────────────┘
│   transcript_   │
│   sources       │
└─────────────────┘
```

---

## 2. Database Schema

### sessions
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| title | VARCHAR(255) | Auto-generated from first message |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Updated on each message |
| is_active | BOOLEAN | Soft-delete flag |
| metadata | JSONB | Future extensibility |

### messages
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| session_id | UUID FK → sessions | CASCADE delete |
| role | VARCHAR(20) | 'user' or 'assistant' |
| content | TEXT | |
| created_at | TIMESTAMPTZ | |
| llm_provider | VARCHAR(50) | Provider that generated response |
| llm_model | VARCHAR(100) | Exact model name |
| latency_ms | INTEGER | End-to-end response time |
| prompt_tokens | INTEGER | |
| completion_tokens | INTEGER | |
| retrieval_hits | INTEGER | Chunks retrieved |
| sources | JSONB | Full source metadata array |

### artifacts
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| session_id | UUID FK → sessions | |
| title | VARCHAR(255) | Extracted from content |
| artifact_type | VARCHAR(20) | 'markdown' or 'html' |
| content | TEXT | Raw generated content |
| sanitized_content | TEXT | bleach-cleaned (HTML only) |
| created_at | TIMESTAMPTZ | |
| source_message_id | UUID FK → messages | Optional link |

### transcript_sources
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| title | VARCHAR(500) | Episode title |
| guest | VARCHAR(255) | Guest name |
| episode_url | VARCHAR(1000) | Source URL |
| published_date | VARCHAR(50) | |
| source_file | VARCHAR(500) | Unique file path |
| chunk_count | INTEGER | |
| ingested_at | TIMESTAMPTZ | |
| content_hash | VARCHAR(64) | SHA-256 for change detection |

---

## 3. API Contracts

All errors return:
```json
{ "error": { "code": "ERROR_CODE", "message": "Human-readable message", "details": {} } }
```

### POST /api/sessions
```json
Request:  { "title": "optional session title" }
Response: { "id": "uuid", "title": "...", "created_at": "...", "updated_at": "...", "message_count": 0 }
```

### POST /api/chat/message
```json
Request:  { "session_id": "uuid", "message": "string", "stream": false }
Response: { "message_id": "uuid", "content": "...", "sources": [...], "retrieval_hits": 5, "provider": "ollama", "model": "llama3.2:3b", "latency_ms": 3200, "grounded": true }
```

### POST /api/chat/stream (SSE)
Events:
```
data: {"type": "metadata", "sources": [...], "retrieval_hits": 5}
data: {"type": "token", "content": "Hello"}
data: {"type": "error", "message": "..."}  # on failure
data: [DONE]
```

### GET /health
```json
{
  "status": "healthy|degraded",
  "components": {
    "database": { "status": "healthy" },
    "vector_store": { "status": "healthy", "chunk_count": 847 },
    "llm": { "status": "healthy", "provider": "ollama", "model": "llama3.2:3b" }
  }
}
```

---

## 4. LLM Abstraction Layer

The single branching point is `app/agent/router.py::get_llm_client()`.

```python
# ONLY place LLM_PROVIDER branching happens:
def get_llm_client() -> BaseLLM:
    if provider == LLMProvider.ANTHROPIC: return AnthropicLLM()
    if provider == LLMProvider.OPENAI:    return OpenAILLM()
    if provider == LLMProvider.OLLAMA:    return OllamaLLM()
```

All business logic (chat agent, skills, tests) calls `get_llm_client()` and uses `BaseLLM.chat()` / `BaseLLM.stream()` exclusively. **No provider-specific code anywhere else.**

To add a new provider:
1. Create `app/agent/newprovider_llm.py` implementing `BaseLLM`
2. Add one `if` branch in `router.py`
3. Add env var in `config.py`
4. No other files need changing.

---

## 5. RAG Retrieval Pipeline

```
data/transcripts/*.txt
        ↓ ingester.py (clean, parse metadata)
TranscriptDocument[]
        ↓ chunker.py (512-token chunks, 64-token overlap)
TranscriptChunk[] (with full provenance)
        ↓ embedder.py (MiniLM-L6-v2 → float32 vectors)
ChromaDB collection "lenny_transcripts"
        ↓ retriever.py (cosine similarity, score threshold 0.3)
RetrievalResult[] (ordered by relevance)
        ↓ chat_agent.py (context injection → LLM)
Grounded response with inline citations
```

**Provenance guarantee:** Every chunk carries: title, guest, date, URL, chunk_id, source_file. This data is returned to the frontend and displayed as clickable source pills.

**Empty retrieval handling:** When no chunks exceed the similarity threshold, `chat_agent.py` returns `_NO_CONTEXT_RESPONSE` — a templated message telling the user what material isn't available and what to do. The LLM is **not called** in this case.

---

## 6. HTML Artifact Security Model

Generated HTML is treated as **untrusted third-party content** because:
- LLMs can be prompted (directly or via jailbreak) to generate malicious HTML
- Even well-intentioned HTML may contain unsafe constructs

**Defense layers:**
1. **Server-side bleach sanitization** (stored in `artifacts.sanitized_content`): strips `<script>`, event handlers, `javascript:` URIs, `data:` URIs
2. **Client-side sandboxed iframe**: `sandbox="allow-scripts"` without `allow-same-origin` — the iframe cannot access parent DOM, localStorage, cookies, or make authenticated requests to the same origin
3. **`referrerpolicy="no-referrer"`**: prevents the iframe content from knowing where it's embedded

What `allow-scripts` permits: CSS transitions, animations, inline event-driven behavior within the iframe itself. What it prevents: everything that could exfiltrate data or modify the parent page.

---

## 7. Deployment Topology

### Development
```
localhost:5173 (Vite HMR)
      ↓
localhost:8000 (Uvicorn with --reload)
      ↓
localhost:5432 (PostgreSQL)
localhost:11434 (Ollama)
./data/embeddings (ChromaDB persistent)
```

### Docker (Production)
```
nginx:80 → frontend static files
     ↓ /api/* → backend:8000 (proxy)
postgres:5432
Ollama: runs on the HOST machine (not containerized)
  accessed via host.docker.internal:11434
ChromaDB: volume-mounted at /app/data/embeddings
```

---

## 8. Failure Modes & Graceful Handling

| Failure | Detection | Response |
|---------|-----------|---------|
| Ollama not running | `httpx.ConnectError` | `503 LLM_UNAVAILABLE` with start instructions |
| Ollama timeout | `httpx.TimeoutException` | `504 LLM_TIMEOUT` |
| Model not pulled | HTTP 404 from Ollama | `503` with `ollama pull {model}` instructions |
| Anthropic auth error | `anthropic.AuthenticationError` | `401 LLM_AUTH_ERROR` |
| DB down | SQLAlchemy connection error | `500 DATABASE_ERROR`; health → degraded |
| Empty vector store | count == 0 | Returns `[]`; chat agent returns no-grounding response |
| Retrieval below threshold | score < `RAG_MIN_SCORE` | Filtered out; treated as empty |
| Artifact generation error | LLM error | `422 ARTIFACT_RENDER_ERROR` |
| ChromaDB build failure | Install error | Document `--only-binary=:all:` workaround |
