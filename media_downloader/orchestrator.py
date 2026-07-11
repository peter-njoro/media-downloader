"""Download orchestrator for the media downloader."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, List, Optional

from media_downloader.download_manager import DownloadManager
from media_downloader.extractors.web import WebPageExtractor
from media_downloader.extractors.web_js import WebPageJSExtractor
from media_downloader.format_selector import FormatSelector
from media_downloader.models import (
    AIAnalysisResult,
    AIConfig,
    AIRecommended,
    DownloadError,
    DownloadOptions,
    DownloadResult,
    DownloadedFiles,
    MediaManifest,
    NoExtractorFound,
    SelectedFormats,
)
from media_downloader.output_resolver import OutputPathResolver
from media_downloader.post_processor import PostProcessor
from media_downloader.registry import ExtractorRegistry
from media_downloader.extractors.generic import GenericHTTPExtractor
from media_downloader.progress import ConsoleProgressReporter, ProgressReporter

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates extraction, selection, download, and post-processing."""

    def __init__(
        self,
        registry: Optional[ExtractorRegistry] = None,
        selector: Optional[FormatSelector] = None,
        download_manager: Optional[DownloadManager] = None,
        output_resolver: Optional[OutputPathResolver] = None,
        post_processor: Optional[PostProcessor] = None,
        ai_config: Optional[AIConfig] = None,
    ) -> None:
        self._registry = registry or ExtractorRegistry()
        self._selector = selector or FormatSelector()
        self._download_manager = download_manager or DownloadManager()
        self._output_resolver = output_resolver or OutputPathResolver()
        self._post_processor = post_processor or PostProcessor()
        self._ai_config = ai_config

    def download(
        self,
        url: str,
        opts: DownloadOptions,
        progress_reporter: Optional[ProgressReporter] = None,
    ) -> DownloadResult:
        # --- Phase 1: Extraction ---
        manifest = self._extract(url, opts)

        # --- Phase 2: Quality advisor (AI-assisted format selection) ---
        if opts.ai_quality and isinstance(opts.quality, AIRecommended):
            manifest = self._ai_quality_advisory(manifest, opts)

        # --- Phase 3: Format selection ---
        selected = self._selector.select(manifest, opts)

        # --- Phase 4: Download ---
        output_dir = opts.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = self._output_resolver.resolve(
            opts.output_template, manifest, output_dir
        )
        reporter = progress_reporter or ConsoleProgressReporter()
        downloaded = self._download_manager.download(
            selected, final_path.parent, opts, reporter
        )

        # --- Phase 5: Post-processing ---
        final_file = self._post_processor.process(downloaded)

        # --- Phase 6: AI content analysis ---
        analysis: Optional[AIAnalysisResult] = None
        if opts.ai_analyze:
            analysis = self._ai_analyze(final_file, opts)

        return DownloadResult(
            final_path=final_file.path,
            manifest=manifest,
            selected_formats=selected,
            bytes_downloaded=downloaded.total_bytes,
            duration_ms=0,
            analysis=analysis,
        )

    def _extract(self, url: str, opts: DownloadOptions) -> MediaManifest:
        """Extract media manifest, with AI fallback on failure."""
        if opts.js_render:
            extractor = WebPageJSExtractor()
            return extractor.extract(url)

        extractor = self._registry.resolve(url)
        if extractor is None:
            if opts.ai_extract:
                return self._ai_extract(url)
            raise NoExtractorFound(url)

        try:
            return extractor.extract(url)
        except Exception:
            if opts.ai_extract:
                logger.info("Standard extraction failed, trying AI extraction")
                return self._ai_extract(url)
            raise

    def _ai_extract(self, url: str) -> MediaManifest:
        """Use AI extractor to find media URLs."""
        from media_downloader.ai_provider import create_provider
        from media_downloader.extractors.ai_extractor import AIExtractor

        if self._ai_config is None:
            raise NoExtractorFound(url)
        provider = create_provider(self._ai_config)
        ai_ext = AIExtractor(provider)
        return ai_ext.extract_with_ai(url)

    def _ai_quality_advisory(
        self, manifest: MediaManifest, opts: DownloadOptions
    ) -> MediaManifest:
        """Use AI to classify content and potentially adjust quality spec."""
        from media_downloader.ai_provider import create_provider
        from media_downloader.quality_advisor import QualityAdvisor

        if self._ai_config is None:
            return manifest
        try:
            provider = create_provider(self._ai_config)
            advisor = QualityAdvisor(provider)
            advice = advisor.advise(manifest)
            if advice.recommended_format_id:
                from media_downloader.models import FormatId
                opts.quality = FormatId(advice.recommended_format_id)
                logger.info(
                    "AI recommends format %s (%s): %s",
                    advice.recommended_format_id,
                    advice.content_type,
                    advice.reasoning,
                )
        except Exception as exc:
            logger.warning("Quality advisory failed, using default: %s", exc)
        return manifest

    def _ai_analyze(
        self, final_file: "FinalFile", opts: DownloadOptions
    ) -> Optional[AIAnalysisResult]:
        """Run AI content analysis on the downloaded file."""
        from media_downloader.ai_provider import create_provider
        from media_downloader.content_analyzer import ContentAnalyzer

        if self._ai_config is None:
            return None
        try:
            provider = create_provider(self._ai_config)
            analyzer = ContentAnalyzer(provider)
            return analyzer.analyze(final_file, opts)
        except Exception as exc:
            logger.warning("Content analysis failed: %s", exc)
            return None

    def download_batch(self, urls: List[str], opts: DownloadOptions) -> List[DownloadResult]:
        return [self.download(url, opts) for url in urls]


def create_orchestrator(ai_config: Optional[AIConfig] = None) -> Orchestrator:
    registry = ExtractorRegistry()
    registry.register(WebPageExtractor())
    registry.register(WebPageJSExtractor())
    registry.register(GenericHTTPExtractor())
    return Orchestrator(registry=registry, ai_config=ai_config)
