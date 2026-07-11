"""
media_downloader — CLI tool and reusable library for downloading video/audio.

Public API surface (expanded as components are implemented):
    - models: all data classes and error types
    - ai_provider: AI provider abstraction
"""

from media_downloader.extractors.generic import GenericHTTPExtractor
from media_downloader.extractors.web import WebPageExtractor
from media_downloader.models import (
    # Enums / discriminated unions
    StreamType,
    QualitySpec,
    Best,
    Worst,
    Height,
    FormatId,
    AIRecommended,
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
    # AI models
    AIConfig,
    AIAnalysisResult,
    AIQualityAdvice,
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
    AIConfigError,
    AIFailure,
    AIQuotaExceeded,
)
from media_downloader.orchestrator import Orchestrator, create_orchestrator
from media_downloader.ai_provider import AIProvider, create_provider

__all__ = [
    "StreamType",
    "QualitySpec",
    "Best",
    "Worst",
    "Height",
    "FormatId",
    "AIRecommended",
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
    "AIConfig",
    "AIAnalysisResult",
    "AIQualityAdvice",
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
    "AIConfigError",
    "AIFailure",
    "AIQuotaExceeded",
    "GenericHTTPExtractor",
    "WebPageExtractor",
    "Orchestrator",
    "create_orchestrator",
    "AIProvider",
    "create_provider",
]
