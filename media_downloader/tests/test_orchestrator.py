from __future__ import annotations

from pathlib import Path

from media_downloader.extractors.base import Extractor
from media_downloader.models import (
    DownloadOptions,
    DownloadedFile,
    DownloadedFiles,
    FinalFile,
    Format,
    MediaManifest,
    StreamType,
)
from media_downloader.orchestrator import Orchestrator
from media_downloader.output_resolver import OutputPathResolver
from media_downloader.post_processor import PostProcessor
from media_downloader.registry import ExtractorRegistry


class _FakeExtractor(Extractor):
    def can_handle(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> MediaManifest:
        return MediaManifest(
            id="demo",
            title="Demo",
            formats=[
                Format(
                    format_id="direct",
                    url="https://example.com/demo.mp4",
                    stream_type=StreamType.VIDEO_ONLY,
                    container="mp4",
                )
            ],
        )


class _FakeDownloadManager:
    def __init__(self) -> None:
        self.received_reporter = None

    def download(self, selected, dest_dir, opts, on_progress=None):
        self.received_reporter = on_progress
        return DownloadedFiles(files=[DownloadedFile(path=dest_dir / "demo.mp4", size=10)], requires_mux=False)


class _FakePostProcessor(PostProcessor):
    def process(self, files: DownloadedFiles) -> FinalFile:
        return FinalFile(path=Path("demo.mp4"), size=10)


class _SpyReporter:
    def __init__(self) -> None:
        self.calls = []

    def on_progress(self, bytes_written: int, total_size: int | None) -> None:
        self.calls.append((bytes_written, total_size))


def test_orchestrator_passes_progress_reporter_to_download_manager(tmp_path) -> None:
    registry = ExtractorRegistry()
    registry.register(_FakeExtractor())
    download_manager = _FakeDownloadManager()
    reporter = _SpyReporter()

    orchestrator = Orchestrator(
        registry=registry,
        download_manager=download_manager,
        output_resolver=OutputPathResolver(),
        post_processor=_FakePostProcessor(),
    )

    orchestrator.download(
        "https://example.com/demo",
        DownloadOptions(output_dir=tmp_path),
        progress_reporter=reporter,
    )

    assert download_manager.received_reporter is reporter
