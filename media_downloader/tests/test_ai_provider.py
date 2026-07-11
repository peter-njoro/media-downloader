"""Tests for AI provider abstraction."""

from __future__ import annotations

import json
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from media_downloader.ai_provider import (
    AIProvider,
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    create_provider,
)
from media_downloader.models import AIConfig, AIConfigError, AIQuotaExceeded


class _FakeProvider(AIProvider):
    """Minimal fake for testing the protocol."""

    def __init__(self, response: str = "ok") -> None:
        self._response = response
        self._calls: List[Dict[str, str]] = []

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        self._calls.extend(messages)
        return self._response

    def name(self) -> str:
        return "fake"


class TestAIOProviderProtocol:
    def test_fake_provider_returns_response(self) -> None:
        p = _FakeProvider("hello")
        result = p.chat([{"role": "user", "content": "hi"}])
        assert result == "hello"

    def test_fake_provider_records_calls(self) -> None:
        p = _FakeProvider()
        p.chat([{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}])
        assert len(p._calls) == 2
        assert p._calls[0]["role"] == "system"


class TestCreateProvider:
    def test_unknown_provider_raises(self) -> None:
        config = AIConfig(provider="nonexistent")
        with pytest.raises(AIConfigError, match="Unknown AI provider"):
            create_provider(config)

    def test_create_openai_provider(self) -> None:
        config = AIConfig(provider="openai", api_key="sk-test")
        p = create_provider(config)
        assert isinstance(p, OpenAIProvider)

    def test_create_anthropic_provider(self) -> None:
        config = AIConfig(provider="anthropic", api_key="sk-ant-test")
        p = create_provider(config)
        assert isinstance(p, AnthropicProvider)

    def test_create_ollama_provider(self) -> None:
        config = AIConfig(provider="ollama")
        p = create_provider(config)
        assert isinstance(p, OllamaProvider)


class TestOpenAIProvider:
    def test_missing_api_key_raises(self) -> None:
        config = AIConfig(provider="openai")
        with pytest.raises(AIConfigError, match="API key required"):
            OpenAIProvider(config)

    def test_name(self) -> None:
        p = OpenAIProvider(AIConfig(provider="openai", api_key="sk-test"))
        assert p.name() == "openai"


class TestAnthropicProvider:
    def test_missing_api_key_raises(self) -> None:
        config = AIConfig(provider="anthropic")
        with pytest.raises(AIConfigError, match="API key required"):
            AnthropicProvider(config)

    def test_name(self) -> None:
        p = AnthropicProvider(AIConfig(provider="anthropic", api_key="sk-ant-test"))
        assert p.name() == "anthropic"


class TestOllamaProvider:
    def test_no_api_key_needed(self) -> None:
        p = OllamaProvider(AIConfig(provider="ollama"))
        assert p.name() == "ollama"
