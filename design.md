# Design Document — Lenny Growth Assistant

## 1. Design Principles

1. **Dark, premium aesthetic** — Knowledge tools should feel confident and focused, not clinical. A dark mode with indigo accents creates a coding-tool aesthetic familiar to technical PMs and engineers.

2. **Information hierarchy** — The most important element (the conversation) gets the most space. Sessions (past context) and artifacts (outputs) occupy defined sidebars.

3. **Trust through transparency** — Source citations are always visible. The active AI provider/model is always shown. When grounding is unavailable, a badge explicitly says so.

4. **Progressive disclosure** — Simple questions get simple answers. Complexity (sources, provider info, security model) is available one click away, not in your face.

5. **Micro-animations for responsiveness** — Typing indicator, fade-ins, hover transforms. The interface should feel alive without being distracting.

---

## 2. Information Architecture

```
App
├── Sidebar (240px)
│   ├── Logo + app name
│   ├── New Chat button (primary CTA)
│   └── Session list (scrollable, newest first)
│
├── Main Area (flex: 1)
│   ├── Header (56px)
│   │   ├── Session title
│   │   └── Provider badge (always visible)
│   ├── Chat Window (scrollable)
│   │   ├── Empty state with suggestion chips
│   │   └── Message bubbles with sources
│   └── Input Area
│       ├── Skill bar (Essay | Markdown | HTML)
│       └── Textarea + Send button
│
└── Artifact Panel (420px, conditional)
    ├── Artifact header + tabs (Preview | Source | Security)
    └── Artifact body (iframe or markdown renderer)
```

---

## 3. Color System

| Token | Value | Use |
|-------|-------|-----|
| `--color-bg-base` | `#09090f` | Page background |
| `--color-bg-surface` | `#111118` | Sidebar, header, input area |
| `--color-bg-elevated` | `#1a1a26` | Cards, dropdowns |
| `--color-accent` | `#6366f1` | Primary buttons, active states |
| `--color-accent-hover` | `#818cf8` | Hover state, source pills |
| `--color-text-primary` | `#f0f0f7` | Main content |
| `--color-text-secondary` | `#a0a0b8` | Secondary labels |
| `--color-text-muted` | `#606078` | Timestamps, metadata |
| `--color-success` | `#34d399` | Provider online dot |
| `--color-warning` | `#fbbf24` | No-grounding badge |
| `--color-error` | `#f87171` | Error banners |

**Glassmorphism:** Used on message bubbles — `backdrop-filter: blur(12px)` with semi-transparent backgrounds creates depth without visual noise.

---

## 4. Typography

- **Primary font:** Inter (Google Fonts) — clean, professional, readable at small sizes
- **Monospace:** System monospace stack — code blocks, artifact source view
- **Scale:** 10px (timestamps) → 11px (labels) → 12px (session titles) → 13px (UI chrome) → 14px (body/messages) → 17px (modal titles)

---

## 5. Component Interaction States

### Message Bubbles
- **User:** Accent-dimmed background, right-aligned, no avatar interaction
- **Assistant (loading):** Three-dot typing animation
- **Assistant (streaming):** Content appears progressively as tokens arrive
- **Assistant (complete):** Sources bar visible; metadata row (provider, latency); no-grounding badge if retrieval failed

### Session List Items
- **Default:** Transparent background
- **Hover:** `rgba(255,255,255,0.07)` glass tint
- **Active:** `rgba(99,102,241,0.15)` accent-tinted background

### Buttons
- **Primary (New Chat, Generate):** Solid accent fill + glow on hover + translateY(-1px) lift
- **Secondary (Cancel, skill buttons):** Glass + border; tint to accent on hover
- **Send button:** Accent fill; disabled (opacity 0.4) when input empty or loading

### Artifact Viewer
- Slides in from the right with `animation: slideInRight 0.3s`
- Tab switching is instant (no animation needed — content is ready)
- Close button removes panel with CSS transition

---

## 6. Responsive Behavior

| Breakpoint | Behavior |
|-----------|---------|
| > 1024px | Full 3-panel layout |
| 768–1024px | Artifact panel narrows to 360px |
| < 768px | Sidebar collapses to icon-only; artifact panel overlays as a drawer |

---

## 7. Accessibility

- All interactive elements have unique `id` attributes (for testing and accessibility)
- `aria-label` on icon-only buttons (send, close artifact)
- `role="button"` + `tabIndex={0}` + `onKeyDown` on session list items
- `sr-only` utility class for screen-reader-only content
- Sufficient color contrast: text-primary on bg-base = 14.5:1 (WCAG AAA)
- Typing indicator uses CSS animation, not JavaScript timers (respects `prefers-reduced-motion` via media query extension opportunity)

---

## 8. Design Decisions & Rationale

**Why 3-panel layout (not 2-panel)?**
Claude's Artifacts panel proved this pattern: conversations generate reusable outputs, and users want to see both simultaneously. A tab-based approach would hide one of the two most important views.

**Why dark mode only?**
The target audience (technical PMs, engineers) overwhelmingly prefers dark mode in productivity tools. Implementing light mode well requires 2× the CSS surface area and was deprioritized for MVP.

**Why glassmorphism on messages?**
Adds visual depth and premium feel without heavy shadows. The `backdrop-filter` is supported by all modern browsers (Baseline Widely Available since 2022).

**Why indigo (`#6366f1`) as accent?**
Indigo sits between blue (trust) and purple (creativity) — appropriate for a knowledge tool that's both analytical and generative. It's also distinct from the "corporate blue" of most enterprise tools.

**Why SSE over WebSocket for streaming?**
Server-Sent Events are HTTP-native, work through most proxies and load balancers without configuration, and are sufficient for our one-directional stream. WebSockets would add complexity without benefit for this use case.

**Why iframe sandbox for HTML artifacts?**
Defense-in-depth: even if bleach misses something, the sandbox prevents XSS from reaching the parent page. `sandbox="allow-scripts"` is the minimal permission set — scripts can run inside the iframe but cannot access the parent DOM, make forms, navigate the top frame, or open popups.
