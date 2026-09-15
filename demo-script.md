# Demo Script — Lenny Growth Assistant
## 2–3 Minute YouTube Demo

**Format:** Screen recording + camera (face visible)  
**Length:** 2:00–2:45  
**Setup:** Have the app running at localhost:5173 with Ollama as the provider

---

## Pre-Recording Checklist

- [ ] Backend running: `make backend`
- [ ] Frontend running: `make frontend`
- [ ] Ollama running: `brew services start ollama && ollama list` (confirm llama3.2:3b is there)
- [ ] Transcripts ingested: `make ingest-stats` (should show > 0 chunks)
- [ ] Provider badge shows "ollama · llama3.2:3b" in top-right
- [ ] Camera on, decent lighting, quiet environment
- [ ] Browser at http://localhost:5173, full screen

---

## Script

### [0:00–0:20] Problem Setup (Camera)
> "Product managers spend hours searching through Lenny's podcast and newsletter to find specific advice. The archive spans hundreds of episodes — there's no way to ask a multi-part question or synthesize advice across guests. I built an AI assistant that changes that."

### [0:20–0:45] App Introduction
*Switch to screen. Show the 3-panel layout.*

> "This is the Lenny Growth Assistant. Notice the provider badge in the top-right — it's currently running on Ollama with llama3.2:3b, completely locally. No API key needed. Let me create a new session and ask a question."

*Click "New Chat".*

### [0:45–1:15] Grounded Q&A Demo
*Type in chat input:* **"What does Lenny's podcast say about retention?"**

> "I'll ask about retention — a fundamental topic covered across many episodes. Watch the source citations that appear below the answer."

*After response appears:*
> "There are the sources — specific episodes, guests, dates. The answer only uses what's in the knowledge base. It doesn't invent quotes."

### [1:15–1:30] No-Hallucination Demo
*Type:* **"What does Lenny think about quantum computing?"**

> "Now I'll ask something that's completely off-topic for Lenny's content."

*After response:*
> "It explicitly says it doesn't have material on this — it won't speculate. This is enforced by the architecture, not just the prompt."

### [1:30–1:50] Ship 30 Essay
*Click "✍️ Ship 30 Essay". Type topic:* **"Why retention beats growth"**

> "Now I'll use the Ship 30 for 30 skill to generate a ~1,250-word Atomic Essay. This is grounded in the same transcripts, structured with a hook, skimmable headings, and a specific takeaway."

*Show the essay as it appears.*

### [1:50–2:10] Artifact Viewer
*Click "🎨 HTML Artifact". Describe:* **"A visual summary dashboard of Lenny's retention insights"**

> "The artifact viewer renders HTML/CSS right beside the chat — like Claude Artifacts, but grounded in Lenny's content. The HTML is sanitized with bleach and served in a sandboxed iframe. No XSS possible."

*Show the Preview and Security tabs.*

### [2:10–2:30] Technical Trade-off (Camera)
> "The most important trade-off I made: I used ChromaDB with local sentence-transformer embeddings instead of a cloud vector store like Pinecone. This means Ollama works completely offline — no API key, no internet, no cost. The trade-off is that the embedding quality is slightly lower than OpenAI's ada-002 embeddings. But for a demo-first system that needs to work reliably without external dependencies, the local-first approach was the right call. Swapping to a cloud embedder is a one-file change."

### [2:30–2:45] Close (Camera)
> "The full source is on GitHub — README covers architecture, setup, tests, and how to add your own transcripts. Built with FastAPI, PostgreSQL, ChromaDB, React, and Anthropic Claude as the cloud option. Thank you."

---

## Recording Tips

- Talk slowly — demos always feel rushed
- Zoom in on the source citations (important differentiator)
- Show the provider badge clearly when discussing Ollama
- If streaming is slow, mention "this is running entirely on your laptop"
- If a response takes > 15s, acknowledge it: "Local inference is a bit slower than cloud"
