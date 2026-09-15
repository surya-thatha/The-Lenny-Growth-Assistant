"""
OpenAI provider implementation.
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError

from app.agent.base import BaseLLM, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.exceptions import LLMAuthError, LLMProviderError, LLMTimeoutError, LLMUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)


class OpenAILLM(BaseLLM):
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise LLMAuthError(
                "OPENAI_API_KEY is not set. "
                "Set it in your .env file or switch LLM_PROVIDER=ollama for local inference."
            )
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return settings.OPENAI_MODEL

    def _to_openai_messages(self, messages: list[LLMMessage], system_prompt: Optional[str]) -> list[dict]:
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for m in messages:
            result.append({"role": m.role, "content": m.content})
        return result

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        t0 = self._now_ms()
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=self._to_openai_messages(messages, system_prompt),
                temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            )
            latency = self._now_ms() - t0
            content = response.choices[0].message.content or ""
            log.info("openai.chat", model=self.model_name, latency_ms=latency)
            return LLMResponse(
                content=content,
                model=self.model_name,
                provider=self.provider_name,
                latency_ms=latency,
                prompt_tokens=response.usage.prompt_tokens if response.usage else None,
                completion_tokens=response.usage.completion_tokens if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
            )
        except AuthenticationError as exc:
            raise LLMAuthError(f"OpenAI authentication failed: {exc}") from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"OpenAI request timed out: {exc}") from exc
        except APIConnectionError as exc:
            raise LLMUnavailableError(f"Cannot connect to OpenAI: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"OpenAI error: {exc}") from exc

    async def stream(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=self.model_name,
                messages=self._to_openai_messages(messages, system_prompt),
                temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except AuthenticationError as exc:
            raise LLMAuthError(f"OpenAI authentication failed: {exc}") from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError(f"OpenAI request timed out: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            await self._client.models.retrieve(self.model_name)
            return True
        except Exception:
            return False
