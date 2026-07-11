"""
AI provider abstraction layer.

Provides a uniform interface for communicating with LLM backends.
SDKs are imported lazily so AI features are only loaded when enabled.
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from media_downloader.models import AIConfig, AIConfigError, AIQuotaExceeded

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0


class AIProvider(ABC):
    """Abstract interface for LLM backends."""

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        """Send a chat completion request and return the assistant's response text.

        Raises AIFailure on provider errors, AIQuotaExceeded on quota exhaustion.
        """

    @abstractmethod
    def name(self) -> str:
        """Return the provider name for logging."""


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProvider(AIProvider):
    """OpenAI API provider (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(self, config: AIConfig) -> None:
        if not config.api_key:
            config.api_key = os.environ.get("OPENAI_API_KEY")
        if not config.api_key:
            raise AIConfigError(
                "OpenAI API key required. Set OPENAI_API_KEY or pass --ai-api-key."
            )
        self._config = config
        self._base_url = config.base_url or "https://api.openai.com/v1"

    def name(self) -> str:
        return "openai"

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        import httpx

        model = model or self._config.model or "gpt-4o-mini"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
        }

        last_exc: Optional[Exception] = None
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES):
            try:
                resp = httpx.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=60.0,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "OpenAI %d (attempt %d/%d), retrying in %.1fs",
                            resp.status_code, attempt + 1, _MAX_RETRIES, backoff,
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    if resp.status_code == 429:
                        raise AIQuotaExceeded("OpenAI rate limit / quota exceeded.")
                    raise AIConfigError(f"OpenAI server error: {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (AIQuotaExceeded, AIConfigError):
                raise
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue

        raise AIConfigError(f"OpenAI request failed after {_MAX_RETRIES} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicProvider(AIProvider):
    """Anthropic API provider (Claude models)."""

    def __init__(self, config: AIConfig) -> None:
        if not config.api_key:
            config.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not config.api_key:
            raise AIConfigError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY or pass --ai-api-key."
            )
        self._config = config
        self._base_url = config.base_url or "https://api.anthropic.com"

    def name(self) -> str:
        return "anthropic"

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        import httpx

        model = model or self._config.model or "claude-sonnet-4-20250514"
        # Anthropic uses a different message format: system is a top-level field
        system_msg = ""
        user_messages: List[Dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append(m)

        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            "messages": user_messages,
        }
        if system_msg:
            payload["system"] = system_msg

        headers = {
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        last_exc: Optional[Exception] = None
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES):
            try:
                resp = httpx.post(
                    f"{self._base_url}/v1/messages",
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "Anthropic %d (attempt %d/%d), retrying in %.1fs",
                            resp.status_code, attempt + 1, _MAX_RETRIES, backoff,
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    if resp.status_code == 429:
                        raise AIQuotaExceeded("Anthropic rate limit / quota exceeded.")
                    raise AIConfigError(f"Anthropic server error: {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                return data["content"][0]["text"]
            except (AIQuotaExceeded, AIConfigError):
                raise
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue

        raise AIConfigError(f"Anthropic request failed after {_MAX_RETRIES} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------


class OllamaProvider(AIProvider):
    """Ollama local provider — no API key needed."""

    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self._base_url = config.base_url or "http://localhost:11434"

    def name(self) -> str:
        return "ollama"

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        import httpx

        model = model or self._config.model or "llama3.1"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": self._config.max_tokens,
                "temperature": self._config.temperature,
            },
        }

        last_exc: Optional[Exception] = None
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES):
            try:
                resp = httpx.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                    timeout=120.0,
                )
                if resp.status_code >= 500:
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "Ollama %d (attempt %d/%d), retrying in %.1fs",
                            resp.status_code, attempt + 1, _MAX_RETRIES, backoff,
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    raise AIConfigError(f"Ollama server error: {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
            except AIConfigError:
                raise
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue

        raise AIConfigError(f"Ollama request failed after {_MAX_RETRIES} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_provider(config: AIConfig) -> AIProvider:
    """Create an AI provider from configuration."""
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
    }
    cls = providers.get(config.provider)
    if cls is None:
        raise AIConfigError(
            f"Unknown AI provider: {config.provider!r}. "
            f"Supported: {', '.join(providers)}"
        )
    return cls(config)
