# Lenny Growth Assistant

> An internal conversational AI assistant grounded in Lenny Rachitsky's Podcast and Newsletter transcripts. Ask complex product-management and growth questions, receive source-cited answers, generate Ship 30-for-30 essays, and create rendered Markdown/HTML artifacts — all in one polished, dark-mode app.

![Architecture](./architecture.md)

---

## Architecture Overview

```
Frontend (React + Vite)  ←→  FastAPI Backend  ←→  PostgreSQL
                                    ↓
                          LLM Abstraction Layer
                       (Ollama | Anthropic | OpenAI)
                                    ↓
                       ChromaDB Vector Store
                    (local sentence-transformer embeddings)
                                    ↓
                      Transcript Knowledge Base
```

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| PostgreSQL | 15 | `brew install postgresql@15` |
| Ollama | latest | `brew install ollama` |
| Docker (optional) | 24+ | [docker.com](https://docker.com) |

---

## Quick Start (Native, no Docker)

```bash
# 1. Clone and enter the project
git clone <repo-url> && cd oogway

# 2. Copy environment template
cp .env.example .env

# 3. Start PostgreSQL and Ollama
brew services start postgresql@15
brew services start ollama
ollama pull llama3.2:3b        # ~2GB first run

# 4. Create the database
make db-create

# 5. Install all dependencies
make setup

# 6. Ingest Lenny transcripts into vector store
make ingest

# 7. Start backend + frontend (two terminals, or use & in background)
make backend   # Terminal 1 → http://localhost:8000
make frontend  # Terminal 2 → http://localhost:5173
```

Open **http://localhost:5173** in your browser.

---

## Quick Start (Docker Compose)

```bash
cp .env.example .env
# Edit .env: set LLM_PROVIDER and any API keys

docker compose up -d
docker compose exec backend python scripts/ingest.py --dir data/transcripts

# App: http://localhost:5173
# API docs: http://localhost:8000/docs
```

---

## Environment Variables

All variables are in `.env.example`. Key ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | Active LLM: `ollama`, `anthropic`, `openai` |
| `OLLAMA_MODEL` | `llama3.2:3b` | Local model name |
| `ANTHROPIC_API_KEY` | — | Required if `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Configurable cloud model |
| `OPENAI_API_KEY` | — | Required if `LLM_PROVIDER=openai` |
| `DATABASE_URL` | `postgresql://lenny:lenny@localhost:5432/lenny_db` | PostgreSQL DSN |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `RAG_TOP_K` | `5` | Chunks retrieved per query |

**Switching providers:** Edit `LLM_PROVIDER` in `.env` and restart the backend. No code changes required.

---

## Cloud LLM Setup

### Anthropic Claude
```bash
# In .env:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### OpenAI
```bash
# In .env:
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### Local Ollama (Demo)
```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b   # or llama3.1:8b for better quality
```

**Fallback behavior:** If Ollama is unavailable (not running), the API returns a `503 LLM_UNAVAILABLE` error with instructions to start Ollama. The frontend shows a clear error message. No hallucination occurs.

---

## Transcript Ingestion

The knowledge base is built from real transcript files. **No content is fabricated.**

### Seed Transcripts (bundled)
Seven curated transcript excerpts are included in `backend/data/transcripts/seed/`:
- Brian Chesky — Founder Mode at Airbnb
- Casey Winters — Science of Growing Products
- Lenny Rachitsky — Finding Product-Market Fit
- Shreyas Doshi — Becoming a Great PM
- Andrew Chen — Network Effects and Growth Loops
- Patrick Collison — Stripe Developer Experience
- Madhavan Ramanujam — Art of Pricing

### Adding Your Own Transcripts
```bash
# Copy transcript files to:
cp my_transcript.txt backend/data/transcripts/user/

# File naming convention (optional, improves metadata):
# YYYY-MM-DD_guest-name_episode-title.txt
# Or use YAML frontmatter at the top of the file:
# ---
# title: Episode Title
# guest: Guest Name
# date: 2024-01-01
# url: https://lennysnewsletter.com/...
# ---

# Re-ingest
make ingest
```

**Paywall note:** Lenny's full transcript archive requires a paid Substack subscription. The ingestion pipeline accepts any `.txt` or `.md` files — if you have access, add them to `data/transcripts/user/` and run `make ingest`.

---

## API Reference

- **Docs:** http://localhost:8000/docs (Swagger UI)
- **ReDoc:** http://localhost:8000/redoc

Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create new chat session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}/messages` | Get session history |
| `POST` | `/api/chat/message` | Send message (blocking) |
| `POST` | `/api/chat/stream` | Send message (SSE streaming) |
| `GET` | `/api/chat/provider` | Active LLM provider info |
| `POST` | `/api/chat/essay` | Generate Ship 30 essay |
| `POST` | `/api/artifacts` | Generate artifact |
| `GET` | `/api/artifacts/{id}` | Get artifact |
| `GET` | `/health` | Full health check |

---

## Running Tests

```bash
# Full test suite
make test

# With coverage
make test-cov

# Specific test
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_main.py::test_create_session -v
```

---

## Troubleshooting

### "Cannot connect to Ollama"
```bash
brew services start ollama
ollama list  # check model is downloaded
ollama pull llama3.2:3b
```

### "Database not ready"
```bash
brew services start postgresql@15
make db-create
```

### "Empty knowledge base"
```bash
make ingest-stats  # check chunk count
make ingest        # run ingestion
```

### Backend won't start — missing module
```bash
cd backend && .venv/bin/pip install -r requirements.txt
```

### ChromaDB build failure on Apple Silicon
```bash
cd backend && .venv/bin/pip install chromadb --only-binary=:all:
```

---

## Project Structure

```
oogway/
├── backend/
│   ├── app/
│   │   ├── api/        # FastAPI routers (chat, sessions, artifacts, health)
│   │   ├── agent/      # LLM abstraction (base, anthropic, ollama, openai, router)
│   │   ├── rag/        # Ingestion, chunking, embedding, retrieval
│   │   ├── skills/     # Ship30 writer, artifact generator
│   │   ├── db/         # SQLAlchemy models, session factory
│   │   └── core/       # Config, logging, exceptions
│   ├── data/transcripts/  # Seed + user transcripts
│   ├── scripts/        # Ingestion CLI
│   └── tests/          # Automated tests
├── frontend/
│   └── src/
│       ├── components/ # ChatWindow, SessionList, ArtifactViewer
│       └── api/        # Typed API client
├── docs/               # Manual test plan
├── agent-transcripts/  # Build logs from this session
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Architecture Trade-offs

1. **ChromaDB vs Pinecone**: ChromaDB runs locally with zero API cost, perfect for demo. Pinecone would add cloud persistence and better scalability — swap by implementing a new `VectorStore` interface.

2. **Sentence-transformers vs OpenAI embeddings**: Local model (all-MiniLM-L6-v2) needs no API key and runs offline. OpenAI ada-002 would give better quality. The embedder is swappable.

3. **SSE streaming vs WebSockets**: SSE is simpler (HTTP-native, no special server needed) and sufficient for our one-directional stream. WebSockets would be needed for bidirectional features.

4. **bleach sanitization**: Chosen over DOMPurify (server-side) for defense-in-depth — HTML is sanitized before storage and before serving. The sandboxed iframe is the client-side layer.

---


