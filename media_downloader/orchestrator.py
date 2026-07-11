"""Download orchestrator for the media downloader."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from media_downloader.download_manager import DownloadManager
from media_downloader.extractors.web import WebPageExtractor
from media_downloader.extractors.web_js import WebPageJSExtractor
from media_downloader.format_selector import FormatSelector
from media_downloader.models import (
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


class Orchestrator:
    """Coordinates extraction, selection, download, and post-processing."""

    def __init__(
        self,
        registry: Optional[ExtractorRegistry] = None,
        selector: Optional[FormatSelector] = None,
        download_manager: Optional[DownloadManager] = None,
        output_resolver: Optional[OutputPathResolver] = None,
        post_processor: Optional[PostProcessor] = None,
    ) -> None:
        self._registry = registry or ExtractorRegistry()
        self._selector = selector or FormatSelector()
        self._download_manager = download_manager or DownloadManager()
        self._output_resolver = output_resolver or OutputPathResolver()
        self._post_processor = post_processor or PostProcessor()

    def download(
        self,
        url: str,
        opts: DownloadOptions,
        progress_reporter: Optional[ProgressReporter] = None,
    ) -> DownloadResult:
        if opts.js_render:
            extractor = WebPageJSExtractor()
        else:
            extractor = self._registry.resolve(url)
            if extractor is None:
                raise NoExtractorFound(url)

        manifest = extractor.extract(url)
        selected = self._selector.select(manifest, opts)
        output_dir = opts.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = self._output_resolver.resolve(opts.output_template, manifest, output_dir)

        reporter = progress_reporter or ConsoleProgressReporter()
        downloaded = self._download_manager.download(selected, final_path.parent, opts, reporter)
        final_file = self._post_processor.process(downloaded)
        return DownloadResult(
            final_path=final_file.path,
            manifest=manifest,
            selected_formats=selected,
            bytes_downloaded=downloaded.total_bytes,
            duration_ms=0,
        )

    def download_batch(self, urls: List[str], opts: DownloadOptions) -> List[DownloadResult]:
        return [self.download(url, opts) for url in urls]


def create_orchestrator() -> Orchestrator:
    registry = ExtractorRegistry()
    registry.register(WebPageExtractor())
    registry.register(WebPageJSExtractor())
    registry.register(GenericHTTPExtractor())
    return Orchestrator(registry=registry)
