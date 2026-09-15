"""
LLM abstraction layer.

All LLM implementations must subclass BaseLLM.
Application code should only import from this module — never import
provider-specific SDKs directly in business logic.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class LLMMessage:
    """A single message in a conversation."""
    role: str  # 'user' | 'assistant' | 'system'
    content: str


@dataclass
class LLMResponse:
    """Standardised response from any LLM provider."""
    content: str
    model: str
    provider: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    raw: Optional[dict] = field(default=None, repr=False)

    @property
    def total_tokens(self) -> Optional[int]:
        if self.prompt_tokens is not None and self.completion_tokens is not None:
            return self.prompt_tokens + self.completion_tokens
        return None


class BaseLLM(ABC):
    """Abstract base for all LLM providers.

    Every provider must implement:
      - chat()        — full blocking response
      - stream()      — async token-by-token generator
      - health_check() — returns True if the provider is reachable

    Providers must NOT be instantiated directly; use get_llm_client() instead.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier, e.g. 'anthropic', 'ollama'."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model currently in use, e.g. 'claude-3-5-sonnet-20241022'."""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Send a list of messages and return a complete response."""

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Yield response tokens as they arrive."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider can serve requests right now."""

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _now_ms() -> int:
        return int(time.monotonic() * 1000)
