"""Web page extractor that discovers downloadable media from HTML pages."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from media_downloader.extractors.base import Extractor
from media_downloader.models import (
    ExtractionError,
    Format,
    MediaManifest,
    NetworkError,
    StreamType,
)


class WebPageExtractor(Extractor):
    """Extracts media from static HTML pages.

    The first version focuses on ordinary, non-JavaScript pages and discovers
    media assets from common HTML patterns such as ``video``, ``audio``,
    ``source``, ``img``, and anchor links.
    """

    _MEDIA_EXTENSIONS = (
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
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".avif",
        ".heic",
        ".heif",
        ".tif",
        ".tiff",
        ".m3u8",
    )

    _AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".opus")
    _VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m3u8")
    _IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".heic", ".heif", ".tif", ".tiff")
    _DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        lower_path = parsed.path.lower()
        if any(lower_path.endswith(ext) for ext in self._MEDIA_EXTENSIONS):
            return False

        if any(part.endswith(ext) for part in lower_path.split("/") if part for ext in self._MEDIA_EXTENSIONS):
            return False

        if lower_path.endswith((".html", ".htm", ".xhtml", ".php", ".asp", ".aspx", ".jsp")):
            return True

        if any(part in {"search", "page", "blog", "post", "index"} for part in lower_path.split("/") if part):
            return True

        return True

    def extract(self, url: str) -> MediaManifest:
        try:
            response_text = self._fetch_page(url)
        except httpx.HTTPError as exc:
            raise NetworkError(url, str(exc)) from exc
        except OSError as exc:
            raise ExtractionError(str(exc)) from exc

        parser = _MediaHTMLParser()
        parser.feed(response_text)
        parser.close()

        candidates = self._normalize_candidates(url, parser.media_urls)
        if not candidates:
            raise ExtractionError(f"No media found in page: {url}")

        formats = []
        for idx, candidate_url in enumerate(candidates, start=1):
            formats.append(
                Format(
                    format_id=f"scraped-{idx}",
                    url=candidate_url,
                    stream_type=self._stream_type(candidate_url),
                    container=self._container(candidate_url),
                )
            )

        return MediaManifest(
            id=url,
            title=parser.title or url,
            formats=formats,
            description=parser.description,
            thumbnail=parser.thumbnail,
        )

    def _fetch_page(self, url: str) -> str:
        with httpx.Client(timeout=10.0, headers=self._DEFAULT_HEADERS) as client:
            response = client.get(url, follow_redirects=True, timeout=10.0)
            response.raise_for_status()
            return response.text

    @classmethod
    def _normalize_candidates(cls, base_url: str, raw_urls: List[Tuple[str, str]]) -> List[str]:
        seen = set()
        normalized = []
        for candidate_url, tag in raw_urls:
            if not candidate_url:
                continue
            full_url = urljoin(base_url, candidate_url)
            if full_url in seen:
                continue
            if not cls._looks_like_media(full_url):
                continue
            if cls._looks_like_html_page(full_url):
                continue
            seen.add(full_url)
            normalized.append(full_url)
        return normalized

    @classmethod
    def _looks_like_media(cls, url: str) -> bool:
        lower_url = url.lower()
        return any(lower_url.endswith(ext) for ext in cls._MEDIA_EXTENSIONS) or any(
            lower_url.rsplit("?", 1)[0].endswith(ext) for ext in cls._MEDIA_EXTENSIONS
        )

    @classmethod
    def _looks_like_html_page(cls, url: str) -> bool:
        lower_url = url.lower()
        if lower_url.endswith((".html", ".htm", ".xhtml", ".php", ".asp", ".aspx", ".jsp")):
            return True
        return any(lower_url.endswith(ext) for ext in (".css", ".js", ".json", ".xml"))

    @classmethod
    def _stream_type(cls, url: str) -> StreamType:
        lower_url = url.lower()
        if any(lower_url.endswith(ext) for ext in cls._AUDIO_EXTENSIONS):
            return StreamType.AUDIO_ONLY
        if any(lower_url.endswith(ext) for ext in cls._IMAGE_EXTENSIONS):
            return StreamType.VIDEO_ONLY
        return StreamType.VIDEO_ONLY

    @classmethod
    def _container(cls, url: str) -> str:
        lower_url = url.lower()
        for ext in cls._MEDIA_EXTENSIONS:
            if lower_url.endswith(ext):
                return ext.lstrip(".")
        return "bin"


class _MediaHTMLParser(HTMLParser):
    """Collects media URLs and basic metadata from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.media_urls: List[Tuple[str, str]] = []
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self.thumbnail: Optional[str] = None
        self._title_parts: List[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = {name: value for name, value in attrs if value is not None}
        lower_tag = tag.lower()

        if lower_tag in {"video", "audio", "source", "img", "a", "link", "iframe"}:
            if lower_tag == "source":
                src = attr_map.get("src")
                if src:
                    self.media_urls.append((src, lower_tag))
            elif lower_tag in {"video", "audio", "img", "iframe"}:
                for attr_name in ("src", "poster"):
                    value = attr_map.get(attr_name)
                    if value:
                        self.media_urls.append((value, lower_tag))
            elif lower_tag == "a":
                href = attr_map.get("href")
                if href:
                    self.media_urls.append((href, lower_tag))
            elif lower_tag == "link":
                href = attr_map.get("href")
                if href:
                    self.media_urls.append((href, lower_tag))

        if lower_tag == "meta":
            meta_name = (attr_map.get("property") or attr_map.get("name") or "").lower()
            content = attr_map.get("content")
            if content and meta_name in {"og:image", "twitter:image", "twitter:image:src"}:
                self.thumbnail = content
            elif content and meta_name in {"og:video", "twitter:player"}:
                self.media_urls.append((content, "meta"))
            elif content and meta_name == "description":
                self.description = content

        if lower_tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def close(self) -> None:
        super().close()
        if self._title_parts:
            self.title = "".join(self._title_parts).strip()
