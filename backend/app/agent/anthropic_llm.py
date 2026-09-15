"""
Anthropic Claude Agent SDK implementation of BaseLLM.
Uses the official Anthropic Claude Agent SDK (claude-agent-sdk) as the primary agent framework.
"""
from __future__ import annotations

import time
from typing import AsyncIterator, Optional

try:
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, query as claude_agent_query
    HAS_CLAUDE_AGENT_SDK = True
except ImportError:
    HAS_CLAUDE_AGENT_SDK = False
    claude_agent_query = None
    ClaudeAgentOptions = None

import anthropic
from anthropic import AsyncAnthropic

from app.agent.base import BaseLLM, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.exceptions import LLMAuthError, LLMProviderError, LLMTimeoutError
from app.core.logging import get_logger

log = get_logger(__name__)


class AnthropicLLM(BaseLLM):
    """
    Anthropic Claude Agent implementation using the official claude-agent-sdk.
    Executes the agent loop with ClaudeAgentOptions and streaming queries.
    """

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise LLMAuthError(
                "ANTHROPIC_API_KEY is not set. "
                "Set it in your .env file or switch LLM_PROVIDER=ollama for local inference."
            )
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.uses_agent_sdk = HAS_CLAUDE_AGENT_SDK

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return settings.ANTHROPIC_MODEL

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Execute chat turn strictly via Claude Agent SDK."""
        t0 = self._now_ms()
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])

        if not HAS_CLAUDE_AGENT_SDK or claude_agent_query is None:
            raise LLMProviderError(
                "claude-agent-sdk is required for LLM_PROVIDER=anthropic. "
                "Install it with: pip install claude-agent-sdk"
            )

        try:
            options = ClaudeAgentOptions(
                system_prompt=system_prompt or "",
                max_turns=settings.MAX_HISTORY_MESSAGES,
            )
            content = ""
            async for msg in claude_agent_query(prompt=prompt_text, options=options):
                if isinstance(msg, str):
                    content += msg
                elif hasattr(msg, "content"):
                    content += str(msg.content)
                elif hasattr(msg, "text"):
                    content += str(msg.text)
                else:
                    content += str(msg)

            latency = self._now_ms() - t0
            log.info(
                "anthropic.agent_sdk_chat",
                model=self.model_name,
                latency_ms=latency,
                framework="claude-agent-sdk",
            )
            return LLMResponse(
                content=content,
                model=self.model_name,
                provider=self.provider_name,
                latency_ms=latency,
                raw={"framework": "claude-agent-sdk"},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError(f"Anthropic authentication failed: {exc}") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(f"Claude Agent SDK request timed out: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Claude Agent SDK execution error: {exc}") from exc

    async def stream(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream tokens strictly via Claude Agent SDK."""
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])

        if not HAS_CLAUDE_AGENT_SDK or claude_agent_query is None:
            raise LLMProviderError(
                "claude-agent-sdk is required for LLM_PROVIDER=anthropic. "
                "Install it with: pip install claude-agent-sdk"
            )

        try:
            options = ClaudeAgentOptions(
                system_prompt=system_prompt or "",
                max_turns=settings.MAX_HISTORY_MESSAGES,
            )
            async for chunk in claude_agent_query(prompt=prompt_text, options=options):
                if isinstance(chunk, str):
                    yield chunk
                elif hasattr(chunk, "text"):
                    yield str(chunk.text)
                elif hasattr(chunk, "content"):
                    yield str(chunk.content)
                else:
                    yield str(chunk)
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError(f"Anthropic authentication failed: {exc}") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(f"Claude Agent SDK request timed out: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Claude Agent SDK streaming error: {exc}") from exc

    async def health_check(self) -> bool:
        """Check availability of Anthropic Claude Agent SDK and credentials."""
        if not settings.ANTHROPIC_API_KEY:
            return False
        try:
            await self._client.messages.create(
                model=self.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
