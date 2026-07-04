from __future__ import annotations

import pytest

from media_downloader.extractors.web import WebPageExtractor
from media_downloader.models import ExtractionError


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.headers = {}

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self._text = (
            "<html><head><title>Sample Page</title>"
            "<meta property='og:image' content='https://cdn.example.com/poster.jpg' />"
            "</head><body>"
            "<video controls><source src='https://cdn.example.com/movie.mp4' type='video/mp4'></video>"
            "<a href='/audio.mp3'>Audio</a>"
            "</body></html>"
        )

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str, follow_redirects: bool = True, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(self._text)


class _FakeClientWithHeaders:
    def __init__(self, *args, **kwargs) -> None:
        self.headers = kwargs.get("headers", {})
        self._text = (
            "<html><head><title>Sample Page</title></head><body>"
            "<a href='https://cdn.example.com/video.mp4'>Video</a></body></html>"
        )

    def __enter__(self) -> "_FakeClientWithHeaders":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str, follow_redirects: bool = True, timeout: float | None = None) -> _FakeResponse:
        assert self.headers.get("User-Agent", "").startswith("Mozilla/")
        return _FakeResponse(self._text)


class _FakeClientNoMedia:
    def __init__(self, *args, **kwargs) -> None:
        self._text = "<html><body><p>No media here</p></body></html>"

    def __enter__(self) -> "_FakeClientNoMedia":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str, follow_redirects: bool = True, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(self._text)


def test_can_handle_relevant_page_urls() -> None:
    extractor = WebPageExtractor()

    assert extractor.can_handle("https://example.com") is True
    assert extractor.can_handle("https://example.com/page.html") is True
    assert extractor.can_handle("https://example.com/video.mp4") is False
    assert extractor.can_handle("https://example.com/audio.mp3") is False


def test_extract_builds_manifest_from_html(monkeypatch) -> None:
    monkeypatch.setattr("media_downloader.extractors.web.httpx.Client", _FakeClient)

    extractor = WebPageExtractor()
    manifest = extractor.extract("https://example.com/page")

    assert manifest.title == "Sample Page"
    assert manifest.thumbnail == "https://cdn.example.com/poster.jpg"
    assert len(manifest.formats) >= 2
    assert any(fmt.url == "https://cdn.example.com/movie.mp4" for fmt in manifest.formats)
    assert any(fmt.url == "https://example.com/audio.mp3" for fmt in manifest.formats)


def test_extract_sends_browser_like_headers(monkeypatch) -> None:
    monkeypatch.setattr("media_downloader.extractors.web.httpx.Client", _FakeClientWithHeaders)

    extractor = WebPageExtractor()
    manifest = extractor.extract("https://example.com/page")

    assert manifest.title == "Sample Page"
    assert len(manifest.formats) == 1


def test_extract_recognizes_avif_media_urls(monkeypatch) -> None:
    class _FakeClientWithAvif:
        def __init__(self, *args, **kwargs) -> None:
            self._text = "<html><body><img src='https://cdn.example.com/photo.avif' /></body></html>"

        def __enter__(self) -> "_FakeClientWithAvif":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, follow_redirects: bool = True, timeout: float | None = None) -> _FakeResponse:
            return _FakeResponse(self._text)

    monkeypatch.setattr("media_downloader.extractors.web.httpx.Client", _FakeClientWithAvif)

    extractor = WebPageExtractor()
    manifest = extractor.extract("https://example.com/page")

    assert any(fmt.container == "avif" for fmt in manifest.formats)


def test_extract_raises_when_no_media_is_found(monkeypatch) -> None:
    monkeypatch.setattr("media_downloader.extractors.web.httpx.Client", _FakeClientNoMedia)

    extractor = WebPageExtractor()

    with pytest.raises(ExtractionError):
        extractor.extract("https://example.com/no-media")
