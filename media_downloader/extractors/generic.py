"""Generic HTTP extractor for direct media URLs."""

from __future__ import annotations

from typing import Optional

import httpx

from media_downloader.extractors.base import Extractor
from media_downloader.models import (
    ExtractionError,
    Format,
    MediaManifest,
    NetworkError,
    StreamType,
)


class GenericHTTPExtractor(Extractor):
    """Extracts a single-format manifest from a direct media URL."""

    def can_handle(self, url: str) -> bool:
        lower = url.lower()
        return any(lower.endswith(ext) for ext in (".mp4", ".webm", ".mkv", ".m4a", ".mp3", ".ogg"))

    def extract(self, url: str) -> MediaManifest:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.head(url, follow_redirects=True)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NetworkError(url, str(exc)) from exc
        except OSError as exc:
            raise ExtractionError(str(exc)) from exc

        content_type = response.headers.get("content-type", "")
        container = self._container_from_content_type(content_type, url)
        size = response.headers.get("content-length")
        file_size = int(size) if size is not None and size.isdigit() else None

        fmt = Format(
            format_id="direct",
            url=url,
            stream_type=StreamType.VIDEO_ONLY if container in {"mp4", "webm", "mkv"} else StreamType.AUDIO_ONLY,
            container=container,
            file_size=file_size,
        )
        return MediaManifest(id=url, title=container.upper(), formats=[fmt])

    @staticmethod
    def _container_from_content_type(content_type: str, url: str) -> str:
        if "audio" in content_type:
            return "m4a" if "mp4" in content_type else "mp3"
        if "video" in content_type:
            return "mp4" if "mp4" in content_type else "webm"
        lower = url.lower()
        for ext in (".mp4", ".webm", ".mkv", ".m4a", ".mp3", ".ogg"):
            if lower.endswith(ext):
                return ext[1:]
        return "bin"
