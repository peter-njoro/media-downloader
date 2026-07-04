"""
Data models for the media downloader.

All models use dataclasses with full type hints. Optional fields use
typing.Optional; list fields use typing.List for broad Python 3.11+ compat.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StreamType(Enum):
    """Describes whether a format carries video, audio, or both."""

    VIDEO_ONLY = "video_only"
    AUDIO_ONLY = "audio_only"
    COMBINED = "combined"


# ---------------------------------------------------------------------------
# QualitySpec — discriminated union represented as a sealed class hierarchy
# ---------------------------------------------------------------------------


class QualitySpec:
    """Base class for quality selection strategies."""


@dataclass(frozen=True)
class Best(QualitySpec):
    """Select the highest-quality available format."""


@dataclass(frozen=True)
class Worst(QualitySpec):
    """Select the lowest-quality available format."""


@dataclass(frozen=True)
class Height(QualitySpec):
    """Select the format closest to the specified pixel height."""

    value: int  # target height in pixels, e.g. 1080


@dataclass(frozen=True)
class FormatId(QualitySpec):
    """Select a specific format by its format_id string."""

    value: str  # exact format_id to select


# ---------------------------------------------------------------------------
# Core media models
# ---------------------------------------------------------------------------


@dataclass
class Format:
    """A single downloadable stream extracted from a media page."""

    format_id: str
    url: str
    stream_type: StreamType
    container: str  # e.g. "mp4", "webm", "m4a"
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    audio_bitrate: Optional[int] = None   # kbps
    video_bitrate: Optional[int] = None   # kbps
    file_size: Optional[int] = None       # bytes
    is_hls: bool = False
    is_dash: bool = False


@dataclass
class MediaManifest:
    """All available streams and metadata extracted from a URL.

    Invariants:
      - id must be non-empty
      - formats must contain at least one element
      - duration must be positive if present
    """

    id: str
    title: str
    formats: List[Format]
    description: Optional[str] = None
    uploader: Optional[str] = None
    duration: Optional[int] = None          # seconds; must be > 0 if set
    thumbnail: Optional[str] = None         # URL string
    extracted_at: datetime.datetime = field(
        default_factory=datetime.datetime.utcnow
    )

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("MediaManifest.id must be non-empty")
        if not self.formats:
            raise ValueError("MediaManifest.formats must contain at least one element")
        if self.duration is not None and self.duration <= 0:
            raise ValueError("MediaManifest.duration must be positive when set")


@dataclass
class DownloadOptions:
    """User-supplied configuration for a download request."""

    quality: QualitySpec = field(default_factory=Best)
    audio_only: bool = False
    audio_format: Optional[str] = None       # e.g. "mp3", "m4a"
    output_template: str = "%(title)s.%(ext)s"
    output_dir: Path = field(default_factory=lambda: Path("."))
    rate_limit: Optional[int] = None         # bytes/sec
    retries: int = 3
    resume: bool = True
    concurrent_fragments: int = 1


@dataclass
class PostProcessOptions:
    """Configuration for FFmpeg-based post-processing steps."""

    audio_format: Optional[str] = None


@dataclass
class SelectedFormats:
    """The result of format selection — what will actually be downloaded.

    Invariant: requires_mux == (video is not None and audio is not None)
    """

    video: Optional[Format] = None
    audio: Optional[Format] = None

    @property
    def requires_mux(self) -> bool:
        """True iff both a separate video and audio track are selected."""
        return self.video is not None and self.audio is not None

    def __post_init__(self) -> None:
        if self.video is None and self.audio is None:
            raise ValueError(
                "SelectedFormats must have at least one of video or audio set"
            )


# ---------------------------------------------------------------------------
# Download lifecycle models
# ---------------------------------------------------------------------------


@dataclass
class DownloadedFile:
    """A single file that has been successfully downloaded."""

    path: Path
    size: int  # bytes on disk


@dataclass
class DownloadedFiles:
    """The collection of files downloaded for a single media item."""

    files: List[DownloadedFile]
    requires_mux: bool

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


@dataclass
class FinalFile:
    """The finished, post-processed output file."""

    path: Path
    size: int  # bytes on disk


@dataclass
class DownloadResult:
    """Final outcome of a completed download operation."""

    final_path: Path
    manifest: MediaManifest
    selected_formats: SelectedFormats
    bytes_downloaded: int
    duration_ms: int


@dataclass
class ResumeState:
    """Persisted state enabling interrupted downloads to continue."""

    url: str
    temp_path: Path
    bytes_written: int
    total_size: Optional[int] = None      # None if Content-Length unknown
    etag: Optional[str] = None
    last_modified: Optional[str] = None   # HTTP date string


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class DownloadError(Exception):
    """Base class for all download-pipeline errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ExtractionError(DownloadError):
    """Raised when an extractor fails to parse a media manifest."""


class SelectionError(DownloadError):
    """Raised when no suitable format can be found for the given options."""


class ProcessingError(DownloadError):
    """Raised when FFmpeg post-processing fails."""


@dataclass
class NoExtractorFound(DownloadError):
    """No registered extractor can handle the given URL."""

    url: str

    def __init__(self, url: str) -> None:
        super().__init__(f"No extractor found for URL: {url}")
        self.url = url


@dataclass
class NetworkError(ExtractionError):
    """A network-level failure occurred during extraction or download."""

    url: str
    cause: str

    def __init__(self, url: str, cause: str) -> None:
        super().__init__(f"Network error for {url}: {cause}")
        self.url = url
        self.cause = cause


@dataclass
class HTTPError(DownloadError):
    """An unexpected HTTP status code was received."""

    url: str
    status_code: int

    def __init__(self, url: str, status_code: int) -> None:
        super().__init__(f"HTTP {status_code} for URL: {url}")
        self.url = url
        self.status_code = status_code


@dataclass
class DiskFull(DownloadError):
    """Write failed because the disk has insufficient free space."""

    path: Path

    def __init__(self, path: Path) -> None:
        super().__init__(f"Disk full while writing to: {path}")
        self.path = path


@dataclass
class NoSuitableFormatFound(SelectionError):
    """Format selection found no format matching the quality constraints."""

    available_heights: List[Optional[int]]

    def __init__(self, available_heights: List[Optional[int]]) -> None:
        heights_str = ", ".join(str(h) for h in available_heights if h is not None)
        super().__init__(
            f"No suitable format found. Available heights: [{heights_str}]"
        )
        self.available_heights = available_heights


@dataclass
class FormatIdNotFound(SelectionError):
    """The requested format_id does not exist in the manifest."""

    format_id: str

    def __init__(self, format_id: str) -> None:
        super().__init__(f"Format ID not found: {format_id}")
        self.format_id = format_id


@dataclass
class ProcessingFailed(ProcessingError):
    """FFmpeg exited with a non-zero code."""

    ffmpeg_stderr: str

    def __init__(self, ffmpeg_stderr: str) -> None:
        super().__init__(f"FFmpeg processing failed:\n{ffmpeg_stderr}")
        self.ffmpeg_stderr = ffmpeg_stderr
