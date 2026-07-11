from __future__ import annotations

from typing import List, Optional
import pytest

from media_downloader.extractors.web_js import WebPageJSExtractor
from media_downloader.models import ExtractionError


class _FakeResponse:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakePage:
    def __init__(
        self,
        dom_results: Optional[List[dict]] = None,
        meta_results: Optional[dict] = None,
        title: str = "JS Page",
        intercepted_urls: Optional[List[str]] = None,
    ) -> None:
        self._dom_results = dom_results if dom_results is not None else [
            {"url": "https://cdn.example.com/video.mp4", "tag": "video"},
        ]
        self._meta_results = meta_results if meta_results is not None else {"description": "A test page"}
        self._title = title
        self._intercepted_urls = intercepted_urls if intercepted_urls is not None else []
        self._handlers: dict = {}

    def on(self, event: str, handler) -> None:
        self._handlers[event] = handler

    def goto(self, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> None:
        handler = self._handlers.get("response")
        if handler:
            for intercepted_url in self._intercepted_urls:
                handler(_FakeResponse(intercepted_url))

    def title(self) -> str:
        return self._title

    def evaluate(self, js_code: str):
        if "tagName" in js_code:
            return self._dom_results
        if "meta" in js_code:
            return self._meta_results
        return {}

    def close(self) -> None:
        pass


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def new_page(self) -> _FakePage:
        return self._page

    def close(self) -> None:
        pass


class _FakeBrowserType:
    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser

    def launch(self, headless: bool = True) -> _FakeBrowser:
        return self._browser


class _FakePlaywright:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.chromium = _FakeBrowserType(browser)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _make_extractor(
    dom_results=None,
    meta_results=None,
    title="JS Page",
    intercepted_urls=None,
):
    page = _FakePage(
        dom_results=dom_results,
        meta_results=meta_results,
        title=title,
        intercepted_urls=intercepted_urls,
    )
    browser = _FakeBrowser(page)
    pw = _FakePlaywright(browser)
    extractor = WebPageJSExtractor(_pw_factory=lambda: pw)
    return extractor, page


def test_can_handle_always_returns_false() -> None:
    extractor = WebPageJSExtractor()
    assert extractor.can_handle("https://example.com") is False
    assert extractor.can_handle("https://example.com/video.mp4") is False
    assert extractor.can_handle("https://example.com/page.html") is False


def test_extract_builds_manifest_from_rendered_dom() -> None:
    extractor, _ = _make_extractor(
        dom_results=[
            {"url": "https://cdn.example.com/movie.mp4", "tag": "video"},
            {"url": "https://cdn.example.com/audio.mp3", "tag": "source"},
        ],
        meta_results={"description": "Test description"},
        title="Test Video Page",
    )

    manifest = extractor.extract("https://example.com/page")

    assert manifest.title == "Test Video Page"
    assert manifest.description == "Test description"
    assert len(manifest.formats) == 2
    assert any(fmt.url == "https://cdn.example.com/movie.mp4" for fmt in manifest.formats)
    assert any(fmt.url == "https://cdn.example.com/audio.mp3" for fmt in manifest.formats)


def test_extract_captures_network_intercepted_urls() -> None:
    extractor, _ = _make_extractor(
        dom_results=[],
        meta_results={},
        intercepted_urls=["https://cdn.example.com/stream.m3u8"],
    )

    manifest = extractor.extract("https://example.com/page")

    assert any(fmt.url == "https://cdn.example.com/stream.m3u8" for fmt in manifest.formats)


def test_extract_raises_when_no_media_found() -> None:
    extractor, _ = _make_extractor(dom_results=[], meta_results={})

    with pytest.raises(ExtractionError):
        extractor.extract("https://example.com/no-media")


def test_extract_deduplicates_dom_and_network_urls() -> None:
    extractor, _ = _make_extractor(
        dom_results=[{"url": "https://cdn.example.com/video.mp4", "tag": "video"}],
        meta_results={},
        intercepted_urls=["https://cdn.example.com/video.mp4"],
    )

    manifest = extractor.extract("https://example.com/page")

    video_urls = [fmt.url for fmt in manifest.formats]
    assert video_urls.count("https://cdn.example.com/video.mp4") == 1


def test_extract_resolves_relative_urls() -> None:
    extractor, _ = _make_extractor(
        dom_results=[{"url": "/media/clip.mp4", "tag": "video"}],
        meta_results={},
    )

    manifest = extractor.extract("https://example.com/page")

    assert any(fmt.url == "https://example.com/media/clip.mp4" for fmt in manifest.formats)


def test_extract_skips_non_media_network_urls() -> None:
    extractor, _ = _make_extractor(
        dom_results=[],
        meta_results={},
        intercepted_urls=["https://cdn.example.com/app.js"],
    )

    with pytest.raises(ExtractionError):
        extractor.extract("https://example.com/page")


def test_extract_extracts_thumbnail_from_meta() -> None:
    extractor, _ = _make_extractor(
        dom_results=[{"url": "https://cdn.example.com/video.mp4", "tag": "video"}],
        meta_results={"thumbnail": "https://cdn.example.com/thumb.jpg"},
    )

    manifest = extractor.extract("https://example.com/page")

    assert manifest.thumbnail == "https://cdn.example.com/thumb.jpg"


def test_extract_falls_back_to_url_as_title() -> None:
    extractor, _ = _make_extractor(
        dom_results=[{"url": "https://cdn.example.com/video.mp4", "tag": "video"}],
        meta_results={},
        title="",
    )

    manifest = extractor.extract("https://example.com/page")

    assert manifest.title == "https://example.com/page"
