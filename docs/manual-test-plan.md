# Manual Test Plan — Lenny Growth Assistant UI

**Version:** 1.0  
**Date:** September 2026  
**Prerequisites:** App running via `docker compose up -d` with ChromaDB ingested (`make ingest`)

---

## Setup Checklist

Before running manual tests, verify:
- [ ] `http://localhost:5173` loads without errors
- [ ] `http://localhost:8000/health/live` returns `{"alive": true}`
- [ ] `http://localhost:8000/health` shows all components `healthy`

---

## Test Suite

### MT-01: First Load — Empty State
**Steps:**
1. Open `http://localhost:5173` in a fresh browser tab
2. Observe the sidebar and main area

**Expected:**
- [ ] Sidebar shows "Lenny" logo and app name
- [ ] "New Chat" button is visible and clickable
- [ ] Session list is empty (no sessions yet)
- [ ] Main area shows a welcome/empty state with suggestion chips
- [ ] Provider badge is visible in the header (e.g., "ollama · llama3.2:3b")
- [ ] No console errors in DevTools

---

### MT-02: Create a New Chat Session
**Steps:**
1. Click "New Chat" button
2. Observe sidebar and main area

**Expected:**
- [ ] New session appears in the sidebar list immediately
- [ ] Session has a default title (e.g., "New Chat" or auto-titled)
- [ ] Chat input field is focused and ready
- [ ] Session list item is highlighted as active

---

### MT-03: Grounded Q&A — Transcript-Covered Topic
**Steps:**
1. In the chat input, type: `How did Airbnb rebuild after COVID?`
2. Press Enter or click Send
3. Wait for response (~5–15 seconds with local Ollama)

**Expected:**
- [ ] Typing indicator (three dots) appears while waiting
- [ ] Response appears with substantive content about Airbnb's COVID recovery
- [ ] At least 1 source citation is shown below the response
- [ ] Source citation shows episode title and guest name
- [ ] Session title in sidebar auto-updates to reflect the question
- [ ] No "Failed to fetch" or network error

---

### MT-04: No-Grounding Response — Uncovered Topic
**Steps:**
1. In a new session, ask: `What is the capital of France?`

**Expected:**
- [ ] Response explicitly states that the topic is not covered in the available transcripts
- [ ] Response does NOT hallucinate or answer with "Paris"
- [ ] No source citations shown
- [ ] A "no grounding" badge or indicator may appear

---

### MT-05: Follow-Up Question — Session History
**Steps:**
1. In an existing session (after MT-03), ask: `What specific tactics did he use?`

**Expected:**
- [ ] Response refers back to the previous message context (Airbnb/Chesky)
- [ ] Response does not ask "who do you mean?" — it uses session history
- [ ] Sources from the original topic are referenced again

---

### MT-06: Multiple Sessions — Persistence
**Steps:**
1. Create 3 separate sessions with different questions in each
2. Reload the browser (`Cmd+R`)
3. Click through each session in the sidebar

**Expected:**
- [ ] All 3 sessions are still listed after reload
- [ ] Each session's full message history is preserved
- [ ] Active session highlights correctly when clicked

---

### MT-07: Ship 30-for-30 Essay Generation
**Steps:**
1. In a chat session, click the "✍️ Ship 30 Essay" skill button
2. Enter topic: `Network effects in marketplace businesses`
3. Submit

**Expected:**
- [ ] Essay response is ~1,000–1,500 words
- [ ] Has a clear hook, body sections with headers, and a "Takeaway" or conclusion
- [ ] Grounded in transcript content with citations
- [ ] No obvious hallucination or filler content

---

### MT-08: Markdown Artifact Generation
**Steps:**
1. Click "📄 Markdown Artifact" skill button
2. Describe: `Create a 1-page summary of the key growth loops from Andrew Chen's episode`
3. Submit

**Expected:**
- [ ] Artifact panel slides in from the right
- [ ] "Preview" tab shows rendered Markdown (headers, bullets, bold text)
- [ ] "Source" tab shows the raw Markdown text
- [ ] Artifact title is displayed in the panel header
- [ ] Panel can be closed with the X button

---

### MT-09: HTML Artifact — Security Sandbox
**Steps:**
1. Click "🎨 HTML Artifact" skill button
2. Describe: `Create a simple dashboard card showing top 3 pricing strategies`
3. Submit

**Expected:**
- [ ] Artifact panel opens showing the rendered HTML in an iframe
- [ ] "Security" tab shows sanitization info
- [ ] `<script>` tags are stripped (verify in "Source" tab — no `<script>` present)
- [ ] Artifact renders visually (not blank)
- [ ] DevTools Console shows no cross-origin errors

---

### MT-10: Provider Badge Accuracy
**Steps:**
1. Check the provider badge in the header
2. In `.env`, change `LLM_PROVIDER=anthropic`, set `ANTHROPIC_API_KEY=sk-ant-test`
3. Restart backend: `docker compose restart backend`
4. Reload frontend

**Expected:**
- [ ] Provider badge updates to show "anthropic"
- [ ] Without a real key, sending a message returns a 401 error — not a crash
- [ ] Error message guides the user to check their API key

---

### MT-11: Ollama Unavailable — Graceful Error
**Steps:**
1. Stop Ollama on the host: `brew services stop ollama` (or kill process)
2. Send a chat message from the frontend

**Expected:**
- [ ] Frontend shows a clear error message (not a generic "Failed to fetch")
- [ ] Error indicates that the LLM provider is unavailable
- [ ] Backend returns 503 (check Network tab in DevTools)
- [ ] App does not crash or freeze

---

### MT-12: Delete Session
**Steps:**
1. Right-click or find the delete option on a session in the sidebar
2. Confirm deletion

**Expected:**
- [ ] Session disappears from the sidebar immediately
- [ ] If it was the active session, the main area shows the empty state
- [ ] Refreshing does not bring the session back

---

### MT-13: Responsive Layout — Narrow Viewport
**Steps:**
1. Open DevTools → Toggle Device Toolbar
2. Set viewport to 768px width
3. Navigate through the app

**Expected:**
- [ ] Sidebar collapses or becomes icon-only
- [ ] Chat window uses full available width
- [ ] Artifact panel overlays rather than appearing beside the chat
- [ ] No horizontal scrollbar on the main content area

---

## Pass Criteria

The manual test session passes if:
- MT-01 through MT-06 all pass (core flows)
- MT-07 or MT-08 passes (at least one skill works)
- MT-11 passes (graceful error handling)
- No browser console errors during normal operation

---

## Known Limitations (Not Test Failures)

| Limitation | Notes |
|---|---|
| Response latency | llama3.2:3b on Mac CPU: 5–20s per response. This is expected. |
| Essay quality | Local 3B model generates adequate but not exceptional essays. Upgrade to `llama3.1:8b` or use Anthropic for better quality. |
| Transcript coverage | Only 7 seed episodes are bundled. Off-topic questions will always produce no-grounding responses. |
| Mobile layout | Below 480px, layout may not be fully optimized (MVP scope). |
