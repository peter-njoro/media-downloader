"""
AI-powered media extractor fallback.

Uses an LLM to reverse-engineer obfuscated media URLs from page source
when standard extraction fails.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from media_downloader.ai_provider import AIProvider
from media_downloader.extractors.base import Extractor
from media_downloader.extractors.web import WebPageExtractor
from media_downloader.models import (
    ExtractionError,
    Format,
    MediaManifest,
    StreamType,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a media URL extraction assistant. Given the following web page source \
(HTML or JavaScript), identify ALL playable media URLs (video and audio streams, \
not thumbnails or UI assets). Return ONLY a JSON object in this exact format:

{
  "urls": [
    {"url": "https://example.com/video.mp4", "type": "video", "quality": "1080p", "container": "mp4", "codec": "h264"},
    {"url": "https://example.com/audio.m4a", "type": "audio", "quality": "high", "container": "m4a", "codec": "aac"}
  ],
  "title": "Page title if found",
  "description": "Page description if found"
}

Rules:
- Include the full absolute URL (not relative paths)
- "type" must be "video" or "audio"
- "quality" is the resolution or bitrate hint if available, or "unknown"
- Only include playable media, not images, scripts, or stylesheets
- If no media found, return {"urls": [], "title": null, "description": null}
"""

_JSON_PATTERN = re.compile(r"\{.*\"urls\".*\}", re.DOTALL)


class AIExtractor(Extractor):
    """Fallback extractor that uses an LLM to find media URLs.

    Unlike other extractors, ``can_handle`` always returns ``False`` —
    this extractor is invoked directly by the orchestrator on failure.
    """

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def can_handle(self, url: str) -> bool:
        return False

    def extract(self, url: str) -> MediaManifest:
        raise NotImplementedError(
            "Use extract_with_ai() for AI-based extraction"
        )

    def extract_with_ai(self, url: str) -> MediaManifest:
        """Fetch page source and use LLM to identify media URLs."""
        source = self._fetch_source(url)
        response_text = self._provider.chat(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": source},
            ]
        )
        parsed = self._parse_response(response_text)
        urls = parsed.get("urls", [])
        title = parsed.get("title") or url
        description = parsed.get("description")

        formats = self._build_formats(urls, url)
        if not formats:
            raise ExtractionError("AI returned no valid media URLs")

        id_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
        return MediaManifest(
            id=f"ai-{id_hash}",
            title=title,
            formats=formats,
            description=description,
        )

    def _fetch_source(self, url: str) -> str:
        """Fetch the raw HTML source of the page."""
        headers = WebPageExtractor._DEFAULT_HEADERS.copy()
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            raise ExtractionError(f"Failed to fetch page source: {exc}") from exc

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from the LLM response, handling markdown code fences."""
        # Try to find JSON in the response (may be wrapped in ```json ... ```)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        # Try direct parse first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        match = _JSON_PATTERN.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse AI response as JSON")
        return {"urls": [], "title": None, "description": None}

    def _build_formats(
        self, urls: List[Dict[str, Any]], base_url: str
    ) -> List[Format]:
        """Convert AI-returned URL dicts into Format objects."""
        formats: List[Format] = []
        seen: set[str] = set()

        for i, entry in enumerate(urls):
            raw_url = entry.get("url", "")
            if not raw_url:
                continue
            full_url = urljoin(base_url, raw_url)
            if full_url in seen:
                continue
            if not WebPageExtractor._looks_like_media(full_url):
                continue
            seen.add(full_url)

            media_type = entry.get("type", "")
            if media_type == "audio":
                stream_type = StreamType.AUDIO_ONLY
            else:
                stream_type = WebPageExtractor._stream_type(full_url)

            container = WebPageExtractor._container(full_url)
            formats.append(
                Format(
                    format_id=f"ai-{i}",
                    url=full_url,
                    stream_type=stream_type,
                    container=container,
                    codec=entry.get("codec"),
                )
            )

        # If exactly one format, use "direct" to match the single-format
        # convention expected by the format selector.
        if len(formats) == 1:
            formats[0].format_id = "direct"

        return formats
