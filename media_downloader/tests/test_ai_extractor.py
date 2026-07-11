"""Tests for AI-powered media extractor."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import pytest

from media_downloader.extractors.ai_extractor import AIExtractor
from media_downloader.models import ExtractionError, MediaManifest


class _FakeAIProvider:
    """Fake AI provider for testing."""

    def __init__(self, response_json: Dict | str = "") -> None:
        if isinstance(response_json, dict):
            self._response = json.dumps(response_json)
        else:
            self._response = response_json
        self._calls: List[Dict[str, str]] = []

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        self._calls.extend(messages)
        return self._response

    def name(self) -> str:
        return "fake"


def _make_extractor(provider: _FakeAIProvider, monkeypatch: pytest.MonkeyPatch) -> AIExtractor:
    """Create an AIExtractor with mocked _fetch_source."""
    ext = AIExtractor(provider)
    monkeypatch.setattr(ext, "_fetch_source", lambda url: "<html>fake page</html>")
    return ext


class TestAIExtractorCanHandle:
    def test_can_handle_always_false(self) -> None:
        provider = _FakeAIProvider({"urls": []})
        ext = AIExtractor(provider)
        assert ext.can_handle("https://example.com/video.mp4") is False
        assert ext.can_handle("https://example.com/page") is False


class TestAIExtractorExtract:
    def test_extract_raises_not_implemented(self) -> None:
        provider = _FakeAIProvider({"urls": []})
        ext = AIExtractor(provider)
        with pytest.raises(NotImplementedError):
            ext.extract("https://example.com/video.mp4")


class TestAIExtractorExtractWithAI:
    def test_extracts_media_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = {
            "urls": [
                {"url": "https://example.com/video.mp4", "type": "video", "quality": "1080p", "container": "mp4"},
                {"url": "https://example.com/audio.m4a", "type": "audio", "quality": "high", "container": "m4a"},
            ],
            "title": "Test Video",
            "description": "A test video",
        }
        provider = _FakeAIProvider(response)
        ext = _make_extractor(provider, monkeypatch)

        manifest = ext.extract_with_ai("https://example.com/page")
        assert isinstance(manifest, MediaManifest)
        assert manifest.title == "Test Video"
        assert manifest.description == "A test video"
        assert len(manifest.formats) == 2
        assert manifest.formats[0].url == "https://example.com/video.mp4"
        assert manifest.formats[1].url == "https://example.com/audio.m4a"

    def test_deduplicates_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = {
            "urls": [
                {"url": "https://example.com/video.mp4", "type": "video"},
                {"url": "https://example.com/video.mp4", "type": "video"},
            ],
            "title": "Test",
        }
        provider = _FakeAIProvider(response)
        ext = _make_extractor(provider, monkeypatch)
        manifest = ext.extract_with_ai("https://example.com/page")
        assert len(manifest.formats) == 1

    def test_filters_non_media_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = {
            "urls": [
                {"url": "https://example.com/style.css", "type": "video"},
                {"url": "https://example.com/video.mp4", "type": "video"},
            ],
            "title": "Test",
        }
        provider = _FakeAIProvider(response)
        ext = _make_extractor(provider, monkeypatch)
        manifest = ext.extract_with_ai("https://example.com/page")
        assert len(manifest.formats) == 1
        assert manifest.formats[0].url == "https://example.com/video.mp4"

    def test_no_valid_urls_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = {"urls": [], "title": "Empty"}
        provider = _FakeAIProvider(response)
        ext = _make_extractor(provider, monkeypatch)
        with pytest.raises(ExtractionError, match="no valid media URLs"):
            ext.extract_with_ai("https://example.com/page")

    def test_handles_markdown_code_fences(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response_text = '```json\n{"urls": [{"url": "https://example.com/v.mp4", "type": "video"}], "title": "Fenced"}\n```'
        provider = _FakeAIProvider(response_text)
        ext = _make_extractor(provider, monkeypatch)
        manifest = ext.extract_with_ai("https://example.com/page")
        assert manifest.title == "Fenced"
        assert len(manifest.formats) == 1

    def test_passes_system_prompt_to_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = {"urls": [], "title": None}
        provider = _FakeAIProvider(response)
        ext = _make_extractor(provider, monkeypatch)
        try:
            ext.extract_with_ai("https://example.com/page")
        except ExtractionError:
            pass
        assert provider._calls[0]["role"] == "system"
        assert "media URL extraction" in provider._calls[0]["content"]
