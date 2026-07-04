"""
Unit tests for ExtractorRegistry (Component 2).

Tests cover:
  - register() appends in order
  - resolve() returns the first matching extractor
  - resolve() returns None when no extractor matches
  - extractors property returns a copy (mutations don't affect registry)
  - registration order is respected (first registered wins)
"""

from __future__ import annotations

import pytest

from media_downloader.models import MediaManifest
from media_downloader.extractors.base import Extractor
from media_downloader.registry import ExtractorRegistry


# ---------------------------------------------------------------------------
# Minimal concrete extractors for testing (no network I/O)
# ---------------------------------------------------------------------------


class _MatchingExtractor(Extractor):
    """Extractor that handles every URL containing a given substring."""

    def __init__(self, match: str, name: str = "") -> None:
        self._match = match
        self.name = name or match

    def can_handle(self, url: str) -> bool:
        return self._match in url

    def extract(self, url: str) -> MediaManifest:  # pragma: no cover
        raise NotImplementedError


class _RejectAllExtractor(Extractor):
    """Extractor that never matches any URL."""

    def can_handle(self, url: str) -> bool:
        return False

    def extract(self, url: str) -> MediaManifest:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_single_extractor(self) -> None:
        registry = ExtractorRegistry()
        extractor = _MatchingExtractor("youtube.com")
        registry.register(extractor)
        assert registry.extractors == [extractor]

    def test_register_multiple_preserves_order(self) -> None:
        registry = ExtractorRegistry()
        a = _MatchingExtractor("a.com", "a")
        b = _MatchingExtractor("b.com", "b")
        c = _MatchingExtractor("c.com", "c")
        registry.register(a)
        registry.register(b)
        registry.register(c)
        assert registry.extractors == [a, b, c]

    def test_register_empty_initially(self) -> None:
        registry = ExtractorRegistry()
        assert registry.extractors == []


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


class TestResolve:
    def test_resolve_returns_none_when_no_extractors(self) -> None:
        registry = ExtractorRegistry()
        assert registry.resolve("https://example.com/video.mp4") is None

    def test_resolve_returns_none_when_no_match(self) -> None:
        registry = ExtractorRegistry()
        registry.register(_RejectAllExtractor())
        assert registry.resolve("https://example.com/video") is None

    def test_resolve_returns_matching_extractor(self) -> None:
        registry = ExtractorRegistry()
        extractor = _MatchingExtractor("youtube.com")
        registry.register(extractor)
        result = registry.resolve("https://www.youtube.com/watch?v=abc123")
        assert result is extractor

    def test_resolve_returns_first_match_in_registration_order(self) -> None:
        """When two extractors both match, the first registered wins."""
        registry = ExtractorRegistry()
        first = _MatchingExtractor("example.com", "first")
        second = _MatchingExtractor("example.com", "second")
        registry.register(first)
        registry.register(second)
        result = registry.resolve("https://example.com/video")
        assert result is first

    def test_resolve_skips_non_matching_extractors(self) -> None:
        """Extractors whose can_handle returns False are skipped."""
        registry = ExtractorRegistry()
        reject = _RejectAllExtractor()
        match = _MatchingExtractor("vimeo.com")
        registry.register(reject)
        registry.register(match)
        result = registry.resolve("https://vimeo.com/123456")
        assert result is match

    def test_resolved_extractor_can_handle_url(self) -> None:
        """P7: any resolved extractor's can_handle must return True for the URL."""
        registry = ExtractorRegistry()
        registry.register(_MatchingExtractor("youtube.com"))
        url = "https://www.youtube.com/watch?v=test"
        extractor = registry.resolve(url)
        assert extractor is not None
        assert extractor.can_handle(url) is True


# ---------------------------------------------------------------------------
# extractors property
# ---------------------------------------------------------------------------


class TestExtractorsProperty:
    def test_extractors_returns_copy(self) -> None:
        """Mutating the returned list must not affect the registry internals."""
        registry = ExtractorRegistry()
        extractor = _MatchingExtractor("example.com")
        registry.register(extractor)

        copy = registry.extractors
        copy.clear()

        # Original registry is unaffected
        assert len(registry.extractors) == 1

    def test_extractors_reflects_registrations(self) -> None:
        registry = ExtractorRegistry()
        assert len(registry.extractors) == 0

        a = _MatchingExtractor("a.com")
        registry.register(a)
        assert len(registry.extractors) == 1

        b = _MatchingExtractor("b.com")
        registry.register(b)
        assert len(registry.extractors) == 2
