"""
media_downloader — CLI tool and reusable library for downloading video/audio.

Public API surface (expanded as components are implemented):
    - models: all data classes and error types
"""

from media_downloader.extractors.generic import GenericHTTPExtractor
from media_downloader.models import (
    # Enums / discriminated unions
    StreamType,
    QualitySpec,
    Best,
    Worst,
    Height,
    FormatId,
    # Core data models
    Format,
    MediaManifest,
    DownloadOptions,
    SelectedFormats,
    DownloadedFile,
    DownloadedFiles,
    FinalFile,
    DownloadResult,
    ResumeState,
    PostProcessOptions,
    # Error hierarchy
    DownloadError,
    ExtractionError,
    SelectionError,
    ProcessingError,
    NoExtractorFound,
    NetworkError,
    HTTPError,
    DiskFull,
    NoSuitableFormatFound,
    FormatIdNotFound,
    ProcessingFailed,
)
from media_downloader.orchestrator import Orchestrator, create_orchestrator

__all__ = [
    "StreamType",
    "QualitySpec",
    "Best",
    "Worst",
    "Height",
    "FormatId",
    "Format",
    "MediaManifest",
    "DownloadOptions",
    "SelectedFormats",
    "DownloadedFile",
    "DownloadedFiles",
    "FinalFile",
    "DownloadResult",
    "ResumeState",
    "PostProcessOptions",
    "DownloadError",
    "ExtractionError",
    "SelectionError",
    "ProcessingError",
    "NoExtractorFound",
    "NetworkError",
    "HTTPError",
    "DiskFull",
    "NoSuitableFormatFound",
    "FormatIdNotFound",
    "ProcessingFailed",
    "GenericHTTPExtractor",
    "Orchestrator",
    "create_orchestrator",
]
