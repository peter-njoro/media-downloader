"""Web page extractor that discovers media using a headless browser for JS-rendered pages."""

from __future__ import annotations

from typing import Callable, List, Optional, Set, Tuple
from urllib.parse import urljoin

from media_downloader.extractors.web import WebPageExtractor
from media_downloader.extractors.base import Extractor
from media_downloader.models import (
    ExtractionError,
    Format,
    MediaManifest,
    NetworkError,
    StreamType,
)


class WebPageJSExtractor(Extractor):
    """Extracts media from JavaScript-rendered pages using Playwright.

    This extractor launches a headless Chromium browser, waits for the page
    to finish rendering, then discovers media through two complementary
    strategies:

    1. **DOM inspection** – queries the rendered DOM for ``<video>``,
       ``<audio>``, ``<source>``, and ``<img>`` elements (same approach
       as the static :class:`WebPageExtractor`, but on the live DOM).
    2. **Network interception** – captures HTTP responses whose URLs match
       known media extensions, catching media loaded dynamically via
       XHR / fetch / AJAX that never appears in the HTML.

    This extractor is **never** auto-selected by the
    :class:`~media_downloader.registry.ExtractorRegistry` – its
    :meth:`can_handle` always returns ``False``.  It is invoked directly
    by the orchestrator when the user passes ``--js``.
    """

    _JS_MEDIA_EXTENSIONS: Tuple[str, ...] = (
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".avi",
        ".m4a",
        ".mp3",
        ".ogg",
        ".wav",
        ".flac",
        ".aac",
        ".opus",
        ".m3u8",
        ".ts",
        ".mpd",
    )

    def __init__(
        self,
        _pw_factory: Optional[Callable] = None,
    ) -> None:
        self._pw_factory = _pw_factory

    def _get_sync_playwright(self) -> Callable:
        if self._pw_factory is not None:
            return self._pw_factory
        try:
            from playwright.sync_api import sync_playwright
            return sync_playwright
        except ImportError as exc:
            raise ExtractionError(
                "playwright is required for JS rendering. "
                "Install it with: pip install playwright && playwright install"
            ) from exc

    def can_handle(self, url: str) -> bool:
        return False

    def extract(self, url: str) -> MediaManifest:
        sync_playwright = self._get_sync_playwright()

        dom_urls: List[Tuple[str, str]] = []
        network_urls: Set[str] = set()
        title: Optional[str] = None
        description: Optional[str] = None
        thumbnail: Optional[str] = None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()

            def _on_response(response) -> None:
                try:
                    resp_url = response.url
                except Exception:
                    return
                lower = resp_url.lower()
                stripped = lower.split("#", 1)[0].split("?", 1)[0]
                if any(stripped.endswith(ext) for ext in self._JS_MEDIA_EXTENSIONS):
                    network_urls.add(resp_url)

            page.on("response", _on_response)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as exc:
                browser.close()
                raise NetworkError(url, str(exc)) from exc

            dom_urls = self._collect_dom_urls(page)
            title = page.title() or None
            meta = self._collect_meta(page)
            if meta.get("description"):
                description = meta["description"]
            if meta.get("thumbnail"):
                thumbnail = meta["thumbnail"]

            browser.close()

        all_raw: List[Tuple[str, str]] = dom_urls + [(u, "network") for u in network_urls]
        candidates = WebPageExtractor._normalize_candidates(url, all_raw)
        if not candidates:
            raise ExtractionError(f"No media found in page: {url}")

        formats = []
        for idx, candidate_url in enumerate(candidates, start=1):
            formats.append(
                Format(
                    format_id=f"js-scraped-{idx}",
                    url=candidate_url,
                    stream_type=WebPageExtractor._stream_type(candidate_url),
                    container=WebPageExtractor._container(candidate_url),
                )
            )

        return MediaManifest(
            id=url,
            title=title or url,
            formats=formats,
            description=description,
            thumbnail=thumbnail,
        )

    @staticmethod
    def _collect_dom_urls(page) -> List[Tuple[str, str]]:
        """Query the rendered DOM for media element URLs."""
        js_code = """() => {
            const results = [];
            const tags = document.querySelectorAll('video, audio, source, img');
            for (const el of tags) {
                const tag = el.tagName.toLowerCase();
                if (tag === 'source') {
                    const src = el.getAttribute('src');
                    if (src) results.push({url: src, tag: tag});
                } else {
                    for (const attr of ['src', 'poster']) {
                        const val = el.getAttribute(attr);
                        if (val) results.push({url: val, tag: tag});
                    }
                }
            }
            return results;
        }"""
        raw = page.evaluate(js_code)
        return [(item["url"], item["tag"]) for item in raw]

    @staticmethod
    def _collect_meta(page) -> dict:
        """Extract OpenGraph and standard meta tags from the rendered page."""
        js_code = """() => {
            const result = {};
            const metas = document.querySelectorAll('meta');
            for (const m of metas) {
                const name = (m.getAttribute('property') || m.getAttribute('name') || '').toLowerCase();
                const content = m.getAttribute('content');
                if (!content) continue;
                if (name === 'og:image' || name === 'twitter:image' || name === 'twitter:image:src') {
                    result.thumbnail = content;
                } else if (name === 'description') {
                    result.description = content;
                }
            }
            return result;
        }"""
        return page.evaluate(js_code)
