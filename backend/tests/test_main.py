"""
Automated tests for critical API, retrieval, routing, and persistence behavior.
Run with: pytest tests/ -v --tb=short
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """Test client with in-memory SQLite for isolation."""
    import os
    # Override DB to use in-memory SQLite for tests
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["CHROMA_PERSIST_DIR"] = "/tmp/test_chroma"

    from app.main import app
    from app.db.database import create_tables
    await create_tables()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Health Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client):
    """Health check must always return a response with component statuses."""
    resp = await client.get("/health")
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert "status" in data
    assert "components" in data
    assert "database" in data["components"]
    assert "vector_store" in data["components"]
    assert "llm" in data["components"]


@pytest.mark.asyncio
async def test_liveness_probe(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["alive"] is True


@pytest.mark.asyncio
async def test_root_endpoint(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "version" in data


# ── Session Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/api/sessions", json={"title": "Test Session"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"]
    assert data["title"] == "Test Session"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_sessions(client):
    # Create a session first
    await client.post("/api/sessions", json={"title": "List Test"})
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_session(client):
    create = await client.post("/api/sessions", json={"title": "Get Test"})
    session_id = create.json()["id"]
    resp = await client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == session_id


@pytest.mark.asyncio
async def test_session_not_found(client):
    resp = await client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_session(client):
    create = await client.post("/api/sessions", json={"title": "Delete Test"})
    session_id = create.json()["id"]
    resp = await client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_session_messages_empty(client):
    create = await client.post("/api/sessions", json={})
    session_id = create.json()["id"]
    resp = await client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Provider Info Test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_info(client):
    resp = await client.get("/api/chat/provider")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "model" in data


# ── Retrieval Tests ───────────────────────────────────────────────────────────

def test_chunker_output_has_provenance():
    """Every chunk must carry full source metadata."""
    from app.rag.ingester import TranscriptDocument
    from app.rag.chunker import chunk_document
    import hashlib

    raw = "This is a test sentence about product management. " * 50
    doc = TranscriptDocument(
        source_file="/fake/test.txt",
        title="Test Episode",
        guest="Test Guest",
        published_date="2024-01-01",
        episode_url="https://example.com",
        content=raw,
        content_hash=hashlib.sha256(raw.encode()).hexdigest(),
    )
    chunks = chunk_document(doc)
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.title == "Test Episode"
        assert chunk.guest == "Test Guest"
        assert chunk.source_file == "/fake/test.txt"
        assert chunk.chunk_id  # Non-empty
        assert len(chunk.content) >= 50


def test_ingester_skips_empty_files(tmp_path):
    """Ingester should skip files with less than 100 chars of content."""
    from app.rag.ingester import load_transcripts
    short = tmp_path / "short.txt"
    short.write_text("Too short.")
    docs = load_transcripts(tmp_path)
    assert len(docs) == 0


def test_ingester_loads_valid_file(tmp_path):
    """Ingester loads a valid transcript file with frontmatter."""
    from app.rag.ingester import load_transcripts
    content = "---\ntitle: Test Episode\nguest: Test Guest\ndate: 2024-01-01\n---\n"
    content += "This is a comprehensive transcript. " * 20
    f = tmp_path / "2024-01-01_test-guest_test-episode.txt"
    f.write_text(content)
    docs = load_transcripts(tmp_path)
    assert len(docs) == 1
    assert docs[0].title == "Test Episode"
    assert docs[0].guest == "Test Guest"


# ── Routing Tests ─────────────────────────────────────────────────────────────

def test_get_llm_client_ollama():
    """Router returns OllamaLLM when provider is ollama."""
    import os
    os.environ["LLM_PROVIDER"] = "ollama"
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    import app.agent.router as router
    reload(router)
    client = router.get_llm_client()
    assert client.provider_name == "ollama"


def test_get_llm_client_missing_anthropic_key():
    """Router raises LLMAuthError when Anthropic key is missing."""
    import os
    os.environ["LLM_PROVIDER"] = "anthropic"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    import app.agent.router as router
    reload(router)
    from app.core.exceptions import LLMAuthError
    with pytest.raises(LLMAuthError):
        router.get_llm_client()


@pytest.mark.asyncio
async def test_anthropic_llm_agent_sdk_structure():
    """Verify AnthropicLLM integrates with claude-agent-sdk interface."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
    os.environ["LLM_PROVIDER"] = "anthropic"
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    from app.agent.anthropic_llm import AnthropicLLM
    from app.agent.base import LLMMessage

    llm = AnthropicLLM()
    assert llm.provider_name == "anthropic"
    assert llm.model_name == "claude-3-5-sonnet-20241022"
    assert hasattr(llm, "uses_agent_sdk")


@pytest.mark.asyncio
async def test_anthropic_llm_runtime_invokes_claude_agent_sdk(monkeypatch):
    """Verify AnthropicLLM.chat() directly invokes claude_agent_sdk.query at runtime."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
    os.environ["LLM_PROVIDER"] = "anthropic"
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    import app.agent.anthropic_llm as anthropic_module
    reload(anthropic_module)
    from app.agent.base import LLMMessage

    invoked_args = {}

    async def mock_claude_agent_query(prompt, options):
        invoked_args["prompt"] = prompt
        invoked_args["options"] = options
        yield "Response generated by Claude Agent SDK"

    monkeypatch.setattr(anthropic_module, "HAS_CLAUDE_AGENT_SDK", True)
    monkeypatch.setattr(anthropic_module, "claude_agent_query", mock_claude_agent_query)

    llm = anthropic_module.AnthropicLLM()
    messages = [LLMMessage(role="user", content="How do network effects work?")]
    system_prompt = "You are Lenny Growth Assistant."

    response = await llm.chat(messages=messages, system_prompt=system_prompt)

    # Assert runtime invocation of Claude Agent SDK
    assert "user: How do network effects work?" in invoked_args["prompt"]
    assert invoked_args["options"].system_prompt == system_prompt
    assert response.content == "Response generated by Claude Agent SDK"
    assert response.provider == "anthropic"
    assert response.raw == {"framework": "claude-agent-sdk"}


@pytest.mark.asyncio
async def test_anthropic_llm_runtime_failure_raises_provider_error(monkeypatch):
    """Verify failures in Claude Agent SDK raise LLMProviderError without silent fallback."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
    os.environ["LLM_PROVIDER"] = "anthropic"
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    import app.agent.anthropic_llm as anthropic_module
    reload(anthropic_module)
    from app.agent.base import LLMMessage
    from app.core.exceptions import LLMProviderError

    async def mock_failing_query(prompt, options):
        raise RuntimeError("Claude Agent SDK runtime execution crashed")
        yield ""

    monkeypatch.setattr(anthropic_module, "HAS_CLAUDE_AGENT_SDK", True)
    monkeypatch.setattr(anthropic_module, "claude_agent_query", mock_failing_query)

    llm = anthropic_module.AnthropicLLM()
    messages = [LLMMessage(role="user", content="Test query")]

    with pytest.raises(LLMProviderError) as exc_info:
        await llm.chat(messages=messages)

    assert "Claude Agent SDK execution error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ollama_provider_remains_active():
    """Verify Ollama provider retains functional local model path."""
    import os
    os.environ["LLM_PROVIDER"] = "ollama"
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    import app.agent.router as router
    reload(router)
    client = router.get_llm_client()
    assert client.provider_name == "ollama"
    assert client.model_name == "llama3.2:3b"




# ── Artifact Sanitization Tests ────────────────────────────────────────────────

def test_html_sanitization_strips_scripts():
    """bleach must strip <script> tags from generated HTML."""
    from app.skills.artifact_generator import sanitize_html
    malicious = '<script>alert("xss")</script><p>Safe content</p>'
    cleaned = sanitize_html(malicious)
    assert "<script" not in cleaned
    assert "Safe content" in cleaned


def test_html_sanitization_strips_event_handlers():
    """Event handler attributes must be removed."""
    from app.skills.artifact_generator import sanitize_html
    malicious = '<div onclick="evil()">Click me</div>'
    cleaned = sanitize_html(malicious)
    assert "onclick" not in cleaned
    assert "Click me" in cleaned


def test_html_sanitization_strips_javascript_hrefs():
    """javascript: URIs must be stripped from href attributes."""
    from app.skills.artifact_generator import sanitize_html
    malicious = '<a href="javascript:alert(1)">Click</a>'
    cleaned = sanitize_html(malicious)
    assert "javascript:" not in cleaned


def test_html_sanitization_allows_safe_content():
    """Safe HTML structure must be preserved."""
    from app.skills.artifact_generator import sanitize_html
    safe = '<div class="container"><h1>Title</h1><p>Content</p></div>'
    cleaned = sanitize_html(safe)
    assert '<div' in cleaned
    assert '<h1>' in cleaned
    assert 'Content' in cleaned


# ── Error Response Format Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_error_response_format(client):
    """All errors must return consistent { error: { code, message } } envelope."""
    resp = await client.get("/api/sessions/not-a-uuid")
    assert resp.status_code in (400, 404, 422)
    data = resp.json()
    # FastAPI validation or our custom error — both should have error info
    assert "error" in data or "detail" in data
