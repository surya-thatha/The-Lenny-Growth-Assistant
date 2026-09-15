# Product Requirements Document — Lenny Growth Assistant

**Version:** 1.0  
**Date:** September 2026  
**Status:** MVP

---

## 1. Problem & Users

**Users:** Product managers, founders, and growth practitioners who regularly consume Lenny Rachitsky's podcast and newsletter content and want to query it conversationally.

**Problem:** Lenny's knowledge base spans hundreds of podcast episodes and newsletter issues. Finding specific advice requires manual search across episodes, bookmarks, and show notes. There is no way to ask multi-part questions, get synthesized answers across multiple episodes, or generate content grounded in this material.

**Opportunity:** A conversational AI assistant that retrieves and synthesizes Lenny's content gives power users a dramatically faster way to apply product and growth insights.

---

## 2. Success Metrics

| Metric | Target |
|--------|--------|
| Time to first grounded answer | < 10s |
| Citation rate (% of answers with sources) | > 90% |
| Hallucination rate (fabricated facts) | 0% — enforced by grounding architecture |
| Session persistence | 100% — all sessions survive restart |
| Artifact render success rate | > 99% |
| Ollama local demo works without internet | ✅ Required |

---

## 3. Assumptions

1. Users have basic product/growth context and want specific, actionable advice.
2. Lenny's content (where accessible) is suitable for RAG without full transcripts.
3. The system should explicitly refuse to speculate beyond retrieved content.
4. HTML artifacts need sanitization to be production-safe.
5. Ship 30-for-30 essay format (Atomic Essays ~1,250 words) is a meaningful output format for PM/growth audiences.

---

## 4. Scope (MVP)

### In Scope
- Conversational Q&A grounded in Lenny transcripts with citations
- Independent persistent chat sessions with preserved history
- Ship 30-for-30 essay generation from retrieved transcript content
- Markdown and HTML/CSS artifact generation with in-app rendering
- Ollama local LLM (mandatory for demo)
- Cloud LLM support (Anthropic Claude, OpenAI)
- Provider-agnostic LLM abstraction with visible provider badge
- PostgreSQL session/message/artifact persistence
- ChromaDB vector store with local embeddings
- Health check endpoints
- Graceful failure handling for all external dependencies

### Out of Scope (v1)
- User authentication / multi-user accounts
- Real-time transcript scraping from Lenny's Substack
- Fine-tuning or model training
- Mobile app
- Sharing / exporting sessions

---

## 5. User Flows

### Flow 1: Grounded Q&A
1. User opens app → sees session list (empty on first run)
2. Clicks "New Chat" → session created in PostgreSQL
3. Types a question about product management or growth
4. Backend retrieves top-k relevant transcript chunks (ChromaDB)
5. LLM generates answer grounded strictly in retrieved chunks
6. Response rendered with source citations in the chat
7. User asks follow-up → session history preserved in context

### Flow 2: Ship 30-for-30 Essay
1. User clicks "✍️ Ship 30 Essay" in skill bar
2. Modal opens → user enters topic and optional angle
3. Backend retrieves transcript context for the topic
4. LLM generates ~1,250-word Atomic Essay using Ship 30 principles
5. Essay appears in chat with source citations

### Flow 3: Artifact Generation
1. User clicks "📄 Markdown Artifact" or "🎨 HTML Artifact"
2. Describes desired artifact content
3. Backend generates artifact and sanitizes HTML if applicable
4. Artifact panel opens beside chat (3-panel layout)
5. User can toggle: Preview | Source | Security tabs

### Flow 4: Provider Switching
1. Engineer edits `LLM_PROVIDER` in `.env`
2. Restarts backend
3. Provider badge in top-right updates automatically
4. All subsequent requests use new provider

---

## 6. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC1 | App starts with `make dev` with no errors after `make setup` |
| AC2 | Creating a session stores it in PostgreSQL |
| AC3 | Sending a message with transcript-covered topic returns answer with ≥1 citation |
| AC4 | Sending a message about uncovered topic returns explicit "I don't have material on this" |
| AC5 | Follow-up question uses session history |
| AC6 | Sessions survive backend restart |
| AC7 | Ship30 essay is ~1,250 words with hook, headings, and a Takeaway section |
| AC8 | Markdown artifact renders correctly in app |
| AC9 | HTML artifact renders in sandboxed iframe (no `allow-same-origin`) |
| AC10 | HTML artifact has `<script>` tags stripped |
| AC11 | Provider badge shows correct provider and model name |
| AC12 | Ollama unavailable → 503 error with clear recovery instructions |
| AC13 | DB unavailable → health endpoint returns `degraded` not crash |
| AC14 | `/health` returns per-component status |
| AC15 | All tests pass with `make test` |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Lenny transcripts behind paywall | Seed with 7 curated public excerpts + ingestion pipeline for user transcripts |
| Ollama model quality for complex PM questions | Use llama3.2:3b minimum; documented upgrade path to llama3.1:8b |
| LLM hallucination | Strict system prompt grounding; explicit no-answer response when retrieval is empty |
| HTML artifact XSS | Server-side bleach sanitization + sandboxed iframe |
| ChromaDB build failures on some OS | Document `--only-binary=:all:` install flag |

---

## 8. Implementation Plan

See [`implementation_plan.md`](./implementation_plan.md) for detailed build order.

**Build order (P0 → P1 → P2):**
1. Core config, logging, exceptions
2. DB models + async session factory
3. LLM abstraction (base → Anthropic → Ollama → OpenAI → router)
4. RAG pipeline (ingester → chunker → embedder/retriever)
5. Chat agent (grounded) + API routes
6. Skills (Ship30 writer + artifact generator)
7. Frontend (React + Vite)
8. Tests
9. Documentation
