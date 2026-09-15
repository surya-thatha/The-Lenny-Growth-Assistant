"""
Ollama provider implementation.
Uses Ollama's REST API directly — no SDK required.
Falls back gracefully when Ollama is unavailable.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional

import httpx

from app.agent.base import BaseLLM, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.exceptions import LLMProviderError, LLMTimeoutError, LLMUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)


def _build_prompt(messages: list[LLMMessage], system_prompt: Optional[str]) -> list[dict]:
    """Convert messages into Ollama's expected chat format."""
    result = []
    if system_prompt:
        result.append({"role": "system", "content": system_prompt})
    for m in messages:
        if m.role == "system":
            result.append({"role": "system", "content": m.content})
        else:
            result.append({"role": m.role, "content": m.content})
    return result


class OllamaLLM(BaseLLM):
    """Ollama local inference provider.

    Connects to the Ollama server at OLLAMA_BASE_URL.
    If the server is unavailable, raises LLMUnavailableError with a clear message
    instructing the user to start Ollama or switch to a cloud provider.
    """

    def __init__(self) -> None:
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._timeout = settings.OLLAMA_TIMEOUT

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return settings.OLLAMA_MODEL

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=5.0),
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        t0 = self._now_ms()
        payload = {
            "model": self.model_name,
            "messages": _build_prompt(messages, system_prompt),
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
                **({"num_predict": max_tokens} if max_tokens else {}),
            },
        }
        try:
            async with self._client() as client:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Is Ollama running? Start it with: brew services start ollama  "
                "Or switch to a cloud provider: LLM_PROVIDER=anthropic"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Ollama request timed out after {self._timeout}s. "
                "The model may still be loading. Try again in a moment."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise LLMUnavailableError(
                    f"Model '{self.model_name}' not found in Ollama. "
                    f"Pull it with: ollama pull {self.model_name}"
                ) from exc
            raise LLMProviderError(f"Ollama HTTP {exc.response.status_code}: {exc.response.text}") from exc

        latency = self._now_ms() - t0
        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")

        log.info(
            "ollama.chat",
            model=self.model_name,
            latency_ms=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return LLMResponse(
            content=content,
            model=self.model_name,
            provider=self.provider_name,
            latency_ms=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=data.get("done_reason"),
            raw=data,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model_name,
            "messages": _build_prompt(messages, system_prompt),
            "stream": True,
            "options": {
                "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
                **({"num_predict": max_tokens} if max_tokens else {}),
            },
        }
        try:
            async with self._client() as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Is Ollama running? Start it with: brew services start ollama"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Ollama stream timed out after {self._timeout}s.") from exc

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=httpx.Timeout(1.0, connect=0.5)) as client:
                r = await client.get("/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """Return list of locally available Ollama models."""
        try:
            async with self._client() as client:
                r = await client.get("/api/tags", timeout=5.0)
                r.raise_for_status()
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []
