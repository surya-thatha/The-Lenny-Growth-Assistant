"""
LLM provider router — the ONLY place where provider-specific branching occurs.
All other application code calls get_llm_client() and works with BaseLLM.
"""
from __future__ import annotations

from functools import lru_cache

from app.agent.base import BaseLLM
from app.core.config import LLMProvider, settings
from app.core.logging import get_logger

log = get_logger(__name__)


def get_llm_client() -> BaseLLM:
    """
    Factory — returns the configured LLM implementation.

    This is the ONLY function in the codebase that branches on LLM_PROVIDER.
    Add new providers here and nowhere else.
    """
    provider = settings.LLM_PROVIDER
    log.info("llm.router", selected_provider=provider.value, model=_model_for(provider))

    if provider == LLMProvider.ANTHROPIC:
        from app.agent.anthropic_llm import AnthropicLLM
        return AnthropicLLM()

    if provider == LLMProvider.OPENAI:
        from app.agent.openai_llm import OpenAILLM
        return OpenAILLM()

    if provider == LLMProvider.OLLAMA:
        from app.agent.ollama_llm import OllamaLLM
        return OllamaLLM()

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Valid options: anthropic, openai, ollama"
    )


def _model_for(provider: LLMProvider) -> str:
    if provider == LLMProvider.ANTHROPIC:
        return settings.ANTHROPIC_MODEL
    if provider == LLMProvider.OPENAI:
        return settings.OPENAI_MODEL
    return settings.OLLAMA_MODEL


def get_provider_info() -> dict:
    """Return current provider/model info for the UI status badge."""
    provider = settings.LLM_PROVIDER
    return {
        "provider": provider.value,
        "model": _model_for(provider),
        "base_url": settings.OLLAMA_BASE_URL if provider == LLMProvider.OLLAMA else None,
    }
