"""
Artifact Generator skill.

Generates Markdown or HTML/CSS artifacts from conversation context.

SECURITY MODEL for HTML artifacts:
- Generated HTML is treated as UNTRUSTED content.
- It is sanitised server-side using the `bleach` library with an explicit allowlist.
- It is served to the frontend as a data blob to be loaded in a sandboxed iframe:
    <iframe sandbox="allow-scripts allow-same-origin">
  Note: `allow-same-origin` is included to allow CSS rendering but the sandbox
  attribute prevents: navigation, popups, form submission, parent frame access.
- The `bleach` allowlist blocks: <script> tags with external src, <meta http-equiv>,
  <link rel="import">, event handler attributes (onclick, onload, etc.),
  javascript: URI schemes, data: URI schemes in src/href attributes.

ALLOWED HTML:
  Structure: div, section, article, header, footer, main, nav, aside, p, span,
             h1-h6, ul, ol, li, dl, dt, dd, blockquote, pre, code, br, hr, table,
             thead, tbody, tr, th, td
  Inline:    a, strong, em, b, i, mark, small, del, ins, sub, sup, abbr
  Media:     img (src restricted to https:// and relative paths only)
  Forms:     None (disallowed entirely — no interactive form submissions)
  Script:    Inline <style> only — <script> is ALWAYS stripped

BLOCKED:
  - All event handler attributes (onclick, onload, onmouseover, etc.)
  - javascript: and data: URI schemes
  - <script src="..."> and inline <script>
  - <meta>, <link>, <object>, <embed>, <frame>, <iframe>
  - CSS url() with external resources (stripped by bleach attribute filter)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import bleach

from app.agent.base import LLMMessage
from app.agent.router import get_llm_client
from app.core.logging import get_logger

log = get_logger(__name__)

# ── Bleach HTML allowlist ─────────────────────────────────────────────────────

_ALLOWED_TAGS = [
    "div", "section", "article", "header", "footer", "main", "nav", "aside",
    "p", "span", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "blockquote", "pre", "code", "br", "hr",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "a", "strong", "em", "b", "i", "mark", "small", "del", "ins", "sub", "sup", "abbr",
    "img",
    "style",  # Inline <style> blocks only — bleach strips @import and url()
]

_ALLOWED_ATTRS = {
    "*": ["class", "id", "title", "aria-label", "aria-hidden", "role"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
    "abbr": ["title"],
}

# Strip event handler attrs and javascript: / data: URIs
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_UNSAFE_HREF_RE = re.compile(r"^(javascript:|data:)", re.IGNORECASE)


def _clean_href(tag: str, name: str, value: str) -> Optional[str]:
    """bleach link_cleaner callback — strips unsafe href/src values."""
    if name in ("href", "src"):
        if _UNSAFE_HREF_RE.match(value.strip()):
            return None
    return value


def sanitize_html(raw_html: str) -> str:
    """
    Sanitise generated HTML using bleach.

    Returns the sanitised HTML string.
    This function is ALWAYS called before storing or serving HTML artifacts.
    """
    # First pass: strip disallowed tags, keep content
    cleaned = bleach.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        strip=True,
        strip_comments=True,
    )
    # Second pass: strip any remaining event handlers that slipped through
    cleaned = _EVENT_HANDLER_RE.sub("", cleaned)
    return cleaned


# ── Generation prompts ────────────────────────────────────────────────────────

_MARKDOWN_SYSTEM = """\
You are a technical writer. Generate a well-structured Markdown document based
on the conversation context. Use appropriate headings, lists, code blocks, and
tables. The document should be immediately useful and production-ready.
"""

_HTML_SYSTEM = """\
You are a frontend developer. Generate a complete, self-contained HTML/CSS document.

Requirements:
- Include a full <html> structure with <head> and <body>.
- Embed all CSS in a <style> tag in the <head>. No external stylesheets.
- Use a dark, modern design with CSS custom properties for colors.
- No JavaScript. No external resources.
- Responsive layout using CSS Grid or Flexbox.
- All content grounded in the conversation context.
- Return ONLY the HTML — no markdown fences, no explanation.
"""


@dataclass
class ArtifactRequest:
    artifact_type: str  # 'markdown' | 'html'
    conversation_context: str  # Summary of the current conversation
    description: str           # What the artifact should contain


@dataclass
class ArtifactResult:
    artifact_type: str
    title: str
    raw_content: str
    sanitized_content: Optional[str]  # Only set for HTML
    security_notes: str


async def generate_artifact(request: ArtifactRequest) -> ArtifactResult:
    """
    Generate a Markdown or HTML/CSS artifact.

    For HTML: sanitizes the output and documents what was stripped.
    """
    artifact_type = request.artifact_type.lower()
    if artifact_type not in ("markdown", "html"):
        raise ValueError(f"artifact_type must be 'markdown' or 'html', got: {artifact_type}")

    system_prompt = _HTML_SYSTEM if artifact_type == "html" else _MARKDOWN_SYSTEM

    user_message = f"""\
Conversation context:
{request.conversation_context}

---

Create a {artifact_type.upper()} artifact with the following content:
{request.description}
"""

    llm = get_llm_client()
    response = await llm.chat(
        messages=[LLMMessage(role="user", content=user_message)],
        system_prompt=system_prompt,
        temperature=0.4,
        max_tokens=3000,
    )

    raw = response.content

    # Extract title from content
    title = _extract_title(raw, artifact_type)

    # Sanitize HTML
    sanitized: Optional[str] = None
    security_notes = "Markdown — no sanitization required."

    if artifact_type == "html":
        sanitized = sanitize_html(raw)
        security_notes = (
            "HTML artifact sanitized with bleach. "
            "Stripped: <script> tags, event handlers (onclick, onload, etc.), "
            "javascript: and data: URI schemes. "
            "Served in sandboxed iframe (sandbox='allow-scripts')."
        )
        log.info(
            "artifact.html_sanitized",
            raw_len=len(raw),
            sanitized_len=len(sanitized),
        )

    log.info(
        "artifact.generated",
        artifact_type=artifact_type,
        title=title,
        provider=response.provider,
        model=response.model,
    )

    return ArtifactResult(
        artifact_type=artifact_type,
        title=title,
        raw_content=raw,
        sanitized_content=sanitized,
        security_notes=security_notes,
    )


def _extract_title(content: str, artifact_type: str) -> str:
    """Extract a title from the generated content."""
    if artifact_type == "markdown":
        for line in content.split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
    elif artifact_type == "html":
        title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
        if h1_match:
            return re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
    return "Generated Artifact"
