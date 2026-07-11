from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from media_downloader.extractors.base import Extractor
from media_downloader.models import (
    AIAnalysisResult,
    AIConfig,
    AIRecommended,
    DownloadOptions,
    DownloadedFile,
    DownloadedFiles,
    FinalFile,
    Format,
    FormatId,
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


class _FailingExtractor(Extractor):
    def can_handle(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> MediaManifest:
        raise RuntimeError("Extraction failed")


class _FakeDownloadManager:
    def __init__(self) -> None:
        self.received_reporter = None

    def download(self, selected, dest_dir, opts, on_progress=None):
        self.received_reporter = on_progress
        return DownloadedFiles(files=[DownloadedFile(path=dest_dir / "demo.mp4", size=10)], requires_mux=False)


class _FakePostProcessor(PostProcessor):
    def process(self, files: DownloadedFiles) -> FinalFile:
        return FinalFile(path=Path("demo.mp4"), size=10)


class _FakeAIProvider:
    def __init__(self, response: str = "ok") -> None:
        self._response = response
        self._calls: List[Dict[str, str]] = []

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        self._calls.extend(messages)
        return self._response

    def name(self) -> str:
        return "fake"


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


class TestOrchestratorAIFallback:
    def test_ai_extract_fallback_on_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import json

        registry = ExtractorRegistry()
        registry.register(_FailingExtractor())
        download_manager = _FakeDownloadManager()

        ai_response = json.dumps({
            "urls": [{"url": "https://example.com/video.mp4", "type": "video", "container": "mp4"}],
            "title": "AI Found",
        })
        fake_provider = _FakeAIProvider(ai_response)

        monkeypatch.setattr(
            "media_downloader.ai_provider.create_provider",
            lambda config: fake_provider,
        )

        # Mock _fetch_source to avoid real HTTP calls
        from media_downloader.extractors.ai_extractor import AIExtractor
        monkeypatch.setattr(AIExtractor, "_fetch_source", lambda self, url: "<html>fake</html>")

        orchestrator = Orchestrator(
            registry=registry,
            download_manager=download_manager,
            output_resolver=OutputPathResolver(),
            post_processor=_FakePostProcessor(),
            ai_config=AIConfig(provider="fake"),
        )

        result = orchestrator.download(
            "https://example.com/page",
            DownloadOptions(output_dir=tmp_path, ai_extract=True),
        )
        assert result.manifest.title == "AI Found"
        assert len(result.manifest.formats) == 1

    def test_no_ai_extract_raises_on_failure(self, tmp_path: Path) -> None:
        registry = ExtractorRegistry()
        registry.register(_FailingExtractor())

        orchestrator = Orchestrator(
            registry=registry,
            download_manager=_FakeDownloadManager(),
            output_resolver=OutputPathResolver(),
            post_processor=_FakePostProcessor(),
        )

        import pytest
        with pytest.raises(RuntimeError, match="Extraction failed"):
            orchestrator.download(
                "https://example.com/page",
                DownloadOptions(output_dir=tmp_path),
            )


class TestOrchestratorAIAnalysis:
    def test_ai_analysis_called_when_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ExtractorRegistry()
        registry.register(_FakeExtractor())

        fake_provider = _FakeAIProvider("Transcription result")
        monkeypatch.setattr(
            "media_downloader.ai_provider.create_provider",
            lambda config: fake_provider,
        )

        # Mock the content analyzer to avoid ffmpeg
        from media_downloader.content_analyzer import ContentAnalyzer
        original_analyze = ContentAnalyzer.analyze

        def mock_analyze(self, final_file, opts):
            return AIAnalysisResult(transcription="Mocked transcript")

        monkeypatch.setattr(ContentAnalyzer, "analyze", mock_analyze)

        orchestrator = Orchestrator(
            registry=registry,
            download_manager=_FakeDownloadManager(),
            output_resolver=OutputPathResolver(),
            post_processor=_FakePostProcessor(),
            ai_config=AIConfig(provider="fake"),
        )

        result = orchestrator.download(
            "https://example.com/video",
            DownloadOptions(output_dir=tmp_path, ai_analyze=True, ai_transcribe=True),
        )

        assert result.analysis is not None
        assert result.analysis.transcription == "Mocked transcript"

    def test_no_analysis_when_disabled(self, tmp_path: Path) -> None:
        registry = ExtractorRegistry()
        registry.register(_FakeExtractor())

        orchestrator = Orchestrator(
            registry=registry,
            download_manager=_FakeDownloadManager(),
            output_resolver=OutputPathResolver(),
            post_processor=_FakePostProcessor(),
        )

        result = orchestrator.download(
            "https://example.com/video",
            DownloadOptions(output_dir=tmp_path),
        )

        assert result.analysis is None


class TestOrchestratorAIQuality:
    def test_ai_quality_adjusts_format_selection(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ExtractorRegistry()

        class _MultiFormatExtractor(Extractor):
            def can_handle(self, url: str) -> bool:
                return True
            def extract(self, url: str) -> MediaManifest:
                return MediaManifest(
                    id="multi",
                    title="Multi Format",
                    formats=[
                        Format(format_id="low", url="https://example.com/low.mp4", stream_type=StreamType.VIDEO_ONLY, container="mp4", height=480),
                        Format(format_id="high", url="https://example.com/high.mp4", stream_type=StreamType.VIDEO_ONLY, container="mp4", height=1080),
                    ],
                )

        registry.register(_MultiFormatExtractor())

        ai_response = '{"content_type": "lecture", "recommended_format_id": "low", "reasoning": "720p for lectures"}'
        fake_provider = _FakeAIProvider(ai_response)
        monkeypatch.setattr(
            "media_downloader.ai_provider.create_provider",
            lambda config: fake_provider,
        )

        orchestrator = Orchestrator(
            registry=registry,
            download_manager=_FakeDownloadManager(),
            output_resolver=OutputPathResolver(),
            post_processor=_FakePostProcessor(),
            ai_config=AIConfig(provider="fake"),
        )

        result = orchestrator.download(
            "https://example.com/lecture",
            DownloadOptions(output_dir=tmp_path, quality=AIRecommended(), ai_quality=True),
        )

        # The quality advisor should have recommended "low" format
        assert result.selected_formats.video is not None
        assert result.selected_formats.video.format_id == "low"
