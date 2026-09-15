"""
Ship 30 for 30 Writing Skill.

This skill encodes the core writing principles from Ship 30 for 30
(https://ship30for30.com) — a programme teaching online writing through
daily "Atomic Essays". Principles encoded below were derived from the
publicly available Ship 30 for 30 curriculum description and methodology.

SOURCED PRINCIPLES (from ship30for30.com public material):
1. Atomic Essays: Each piece covers a single, focused idea. Not a thread, not
   a listicle, not a multi-topic explainer — one idea explored completely.
2. Strong Hook: The first 1-2 sentences must stop the scroll. Specificity beats
   vagueness. Use a counter-intuitive claim, a surprising statistic, or a
   concrete situation the reader recognises.
3. Skimmability: Readers skim before they read. Short paragraphs (1-3 sentences),
   bold for key claims, whitespace as a design element, numbered/bulleted lists.
4. Specific Takeaway: Every essay must end with a concrete, actionable insight.
   Not "think about this" — "do this specific thing".
5. Proof Over Assertion: Back every claim with evidence — data, a story, a
   named example. In this context: transcript citations from Lenny's podcast.
6. Cut Ruthlessly: No throat-clearing, no meta-commentary ("In this essay I will
   discuss..."), no adverbs where a stronger verb works.
7. Narrative Arc: Even short essays need a beginning (hook), middle (evidence
   and exploration), and end (concrete takeaway).

Target length: ~1,250 words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.agent.base import LLMMessage
from app.agent.router import get_llm_client
from app.core.logging import get_logger
from app.rag.embedder import RetrievalResult, retrieve

log = get_logger(__name__)

_SHIP30_SYSTEM_PROMPT = """\
You are an expert online writer trained in the Ship 30 for 30 methodology.
Your task is to write an Atomic Essay of approximately 1,250 words.

## SHIP 30 FOR 30 WRITING PRINCIPLES (apply all of them)

**1. ONE IDEA ONLY**
Each essay covers a single, sharply defined idea. Do not scope-creep into
adjacent topics. Choose the sharpest version of the premise.

**2. HOOK THAT STOPS THE SCROLL**
Your opening line must create immediate curiosity or recognition.
Formats that work:
  - Counter-intuitive claim: "Most product managers measure the wrong thing."
  - Specific situation: "Last Tuesday, Brian Chesky told 10 million Airbnb hosts they were wrong."
  - Provocative question that the essay will answer definitively.
Do NOT start with "In this essay..." or a definition.

**3. SKIMMABLE STRUCTURE**
  - Use 2-3 subheadings (## format) to break the essay.
  - Short paragraphs: 1-3 sentences maximum.
  - Bold the single most important sentence in each section.
  - Use numbered lists or bullets for multi-part insights.
  - Whitespace is your friend — avoid walls of text.

**4. EVIDENCE, NOT ASSERTION**
Every claim must be backed by the provided transcript evidence.
Cite sources inline: [Source: "Episode Title" with Guest (Date)]
Do not add claims not supported by the provided context.

**5. CONCRETE TAKEAWAY**
The final section must be titled "## The Takeaway" and contain:
  - One specific, actionable thing the reader can do this week.
  - Not abstract advice — a named action with a described outcome.

**6. LEAN AND DIRECT**
  - No throat-clearing ("I want to talk about...", "It's important to note...")
  - No passive voice where active works.
  - Cut adverbs; choose a stronger verb.
  - Target 1,100–1,350 words total.

## GROUNDING RULES
Use ONLY the transcript excerpts provided. If the context is insufficient
for a specific claim, omit the claim rather than fabricating it.
"""


@dataclass
class EssayRequest:
    topic: str
    session_context: Optional[str] = None  # Prior conversation summary
    custom_angle: Optional[str] = None     # Specific angle requested by user


@dataclass
class EssayResult:
    content: str
    word_count: int
    sources: list[dict]
    topic: str
    retrieval_hits: int


def _count_words(text: str) -> int:
    return len(re.findall(r"\w+", text))


async def write_essay(request: EssayRequest) -> EssayResult:
    """
    Generate a Ship 30 for 30 Atomic Essay grounded in Lenny transcripts.

    Process:
    1. Retrieve relevant transcript chunks for the topic.
    2. Build a context block from retrieved material.
    3. Instruct the LLM using Ship 30 principles system prompt.
    4. Return the essay with word count and source citations.
    """
    # Retrieve transcript context
    results: list[RetrievalResult] = retrieve(request.topic, top_k=8)

    if not results:
        log.warning("ship30.no_context", topic=request.topic)
        no_context_essay = f"""\
## On {request.topic}

*Note: The Lenny transcript knowledge base does not contain sufficient material \
on this specific topic to write a properly grounded essay. The essay below \
would require fabrication — which this assistant does not do.*

**To get a grounded essay:**
1. Add relevant Lenny transcript files to `data/transcripts/user/`
2. Run `make ingest` to index them
3. Request the essay again

For now, you can search [lennysnewsletter.com](https://www.lennysnewsletter.com) \
for episodes on this topic.
"""
        return EssayResult(
            content=no_context_essay,
            word_count=_count_words(no_context_essay),
            sources=[],
            topic=request.topic,
            retrieval_hits=0,
        )

    # Build context block
    context_lines = ["<transcript_evidence>"]
    for i, r in enumerate(results, 1):
        context_lines.append(f"\n[Evidence {i}] Source: {r.citation}")
        if r.episode_url:
            context_lines.append(f"URL: {r.episode_url}")
        context_lines.append(f"\n{r.content}")
    context_lines.append("\n</transcript_evidence>")
    context_block = "\n".join(context_lines)

    angle = f"\nSpecific angle to explore: {request.custom_angle}" if request.custom_angle else ""
    session_ctx = f"\nConversation context: {request.session_context}" if request.session_context else ""

    user_message = f"""\
{context_block}

---

Write a Ship 30 for 30 Atomic Essay on the following topic:
**Topic: {request.topic}**{angle}{session_ctx}

Requirements:
- Approximately 1,250 words
- Strong hook in the first 1-2 sentences
- 2-3 subheadings using Ship 30 structure
- Every factual claim cited with [Source: ...]
- End with ## The Takeaway — one specific, actionable insight
- Use ONLY the provided transcript evidence for factual claims
"""

    llm = get_llm_client()
    response = await llm.chat(
        messages=[LLMMessage(role="user", content=user_message)],
        system_prompt=_SHIP30_SYSTEM_PROMPT,
        temperature=0.6,  # Slightly higher for writing creativity
        max_tokens=2000,
    )

    word_count = _count_words(response.content)
    log.info(
        "ship30.essay_generated",
        topic=request.topic,
        word_count=word_count,
        retrieval_hits=len(results),
        provider=response.provider,
        model=response.model,
    )

    return EssayResult(
        content=response.content,
        word_count=word_count,
        sources=[r.to_dict() for r in results],
        topic=request.topic,
        retrieval_hits=len(results),
    )
