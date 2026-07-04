"""Generic HTTP extractor for direct media URLs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

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

    _KNOWN_EXTENSIONS = (
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
    )

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        lower_path = parsed.path.lower()
        lower_query = parsed.query.lower()
        path_parts = [part for part in lower_path.split("/") if part]

        if any(lower_path.endswith(ext) for ext in self._KNOWN_EXTENSIONS):
            return True

        if any(part.endswith(ext) for part in path_parts for ext in self._KNOWN_EXTENSIONS):
            return True

        if any(part in {"video", "audio", "media", "stream", "image", "images"} for part in path_parts):
            return True

        if re.search(r"(?:^|/)(video|audio|media|stream|image|images)(?:/|$)", lower_path):
            return True

        if re.search(r"(?:^|[?&])(video|audio|media|stream|image|images)(?:=|&|$)", lower_query):
            return True

        if any(host in parsed.netloc.lower() for host in ("pexels.com", "images", "cdn", "media")):
            return True

        return False

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

    @classmethod
    def _container_from_content_type(cls, content_type: str, url: str) -> str:
        lower_type = content_type.lower()
        if "audio" in lower_type:
            return "m4a" if "mp4" in lower_type else "mp3"
        if "video" in lower_type:
            return "mp4" if "mp4" in lower_type else "webm"
        if "image/jpeg" in lower_type:
            return "jpeg"
        if "image/png" in lower_type:
            return "png"
        if "image/webp" in lower_type:
            return "webp"
        if "image/gif" in lower_type:
            return "gif"
        if "image/bmp" in lower_type:
            return "bmp"
        if "image/avif" in lower_type:
            return "avif"
        if "image/heic" in lower_type:
            return "heic"
        if "image/heif" in lower_type:
            return "heif"
        if "image/tiff" in lower_type:
            return "tiff"

        lower = url.lower()
        for ext in cls._KNOWN_EXTENSIONS:
            if lower.endswith(ext):
                return ext[1:]

        parsed = urlparse(url)
        path = parsed.path.lower()
        if path.endswith("/video"):
            return "mp4"
        if path.endswith("/audio"):
            return "mp3"
        if path.endswith("/image"):
            return "jpg"
        return "bin"
