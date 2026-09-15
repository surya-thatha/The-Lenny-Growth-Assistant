"""
Transcript ingestion pipeline.

Loads .txt and .md files from data/transcripts/.
Extracts metadata from filenames following the convention:
  YYYY-MM-DD_guest-name_episode-title.txt
  e.g.: 2023-05-15_brian-chesky_airbnb-founder-mode.txt

Content is cleaned (timestamps removed, whitespace normalised) and returned as
TranscriptDocument objects ready for chunking.

IMPORTANT: This ingester only loads files that physically exist on disk.
It never fabricates or invents transcript content.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

log = get_logger(__name__)

# Regex to strip podcast-style timestamps like [00:01:23] or (12:34)
_TS_RE = re.compile(r"\[?\(?\d{1,2}:\d{2}(?::\d{2})?\]?\)?")
# Remove speaker cues like "LENNY:" or "BRIAN:" at line start
_SPEAKER_LABEL_RE = re.compile(r"^[A-Z][A-Z\s]{1,30}:\s*", re.MULTILINE)


@dataclass
class TranscriptDocument:
    """A fully-cleaned transcript document with source provenance."""

    source_file: str           # Absolute path to the source file
    title: str
    guest: Optional[str]
    published_date: Optional[str]
    episode_url: Optional[str]
    content: str               # Cleaned text
    content_hash: str          # SHA-256 of original content for change detection
    raw_content: str = field(repr=False, default="")  # Original uncleaned text


def _parse_filename(path: Path) -> dict:
    """Extract metadata from filename convention: YYYY-MM-DD_guest_title.txt"""
    stem = path.stem
    parts = stem.split("_", maxsplit=2)
    meta: dict = {"published_date": None, "guest": None, "title": stem, "episode_url": None}

    if len(parts) >= 1 and re.match(r"\d{4}-\d{2}-\d{2}", parts[0]):
        meta["published_date"] = parts[0]
    if len(parts) >= 2:
        meta["guest"] = parts[1].replace("-", " ").title()
    if len(parts) >= 3:
        meta["title"] = parts[2].replace("-", " ").title()
    elif len(parts) == 2:
        meta["title"] = f"Lenny's Podcast with {meta['guest']}"

    return meta


def _read_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse optional YAML-like frontmatter from transcript files.
    Supported keys: title, guest, date, url
    """
    meta: dict = {}
    if not content.startswith("---"):
        return meta, content

    lines = content.split("\n")
    end = 0
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end == 0:
        return meta, content

    for line in lines[1:end]:
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()

    return meta, "\n".join(lines[end + 1:]).strip()


def _clean_content(raw: str) -> str:
    """Strip timestamps, normalise whitespace, collapse blank lines."""
    text = _TS_RE.sub("", raw)
    text = _SPEAKER_LABEL_RE.sub("", text)
    # Collapse multiple spaces
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Collapse more than 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_transcripts(transcript_dir: str | Path) -> list[TranscriptDocument]:
    """
    Load all .txt and .md files from transcript_dir recursively.

    Returns a list of TranscriptDocument objects.
    Skips files that fail to parse and logs the error — never crashes.
    """
    base = Path(transcript_dir)
    if not base.exists():
        log.warning("ingester.dir_not_found", path=str(base))
        return []

    docs: list[TranscriptDocument] = []
    for path in sorted(base.rglob("*.txt")) + sorted(base.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            content_hash = hashlib.sha256(raw.encode()).hexdigest()

            fm_meta, body = _read_frontmatter(raw)
            fn_meta = _parse_filename(path)

            title = fm_meta.get("title") or fn_meta["title"]
            guest = fm_meta.get("guest") or fn_meta["guest"]
            date = fm_meta.get("date") or fn_meta["published_date"]
            url = fm_meta.get("url") or fn_meta["episode_url"]

            cleaned = _clean_content(body)
            if len(cleaned) < 100:
                log.warning("ingester.skipped_too_short", path=str(path), chars=len(cleaned))
                continue

            docs.append(
                TranscriptDocument(
                    source_file=str(path),
                    title=title,
                    guest=guest,
                    published_date=date,
                    episode_url=url,
                    content=cleaned,
                    content_hash=content_hash,
                    raw_content=raw,
                )
            )
            log.info("ingester.loaded", path=path.name, chars=len(cleaned))
        except Exception as exc:
            log.error("ingester.error", path=str(path), error=str(exc))

    log.info("ingester.summary", total_docs=len(docs))
    return docs
