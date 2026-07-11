"""Tests for content analyzer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from media_downloader.content_analyzer import ContentAnalyzer
from media_downloader.models import AIAnalysisResult, DownloadOptions, FinalFile


class _FakeAIProvider:
    def __init__(self, response: str = "Transcript text here") -> None:
        self._response = response
        self._calls: List[Dict[str, str]] = []

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        self._calls.extend(messages)
        return self._response

    def name(self) -> str:
        return "fake"


def _opts(**kwargs: bool) -> DownloadOptions:
    defaults = {
        "ai_transcribe": False,
        "ai_summarize": False,
        "ai_thumbnails": False,
        "ai_analyze": False,
    }
    defaults.update(kwargs)
    return DownloadOptions(**defaults)


class TestContentAnalyzerModes:
    def test_no_modes_enabled_returns_empty(self, tmp_path: Path) -> None:
        provider = _FakeAIProvider()
        analyzer = ContentAnalyzer(provider)
        final_file = FinalFile(path=tmp_path / "video.mp4", size=1000)
        result = analyzer.analyze(final_file, _opts())
        assert result.transcription is None
        assert result.summary is None
        assert result.thumbnails == []

    def test_transcribe_no_ffmpeg_returns_none(self, tmp_path: Path) -> None:
        provider = _FakeAIProvider("Hello world transcript")
        analyzer = ContentAnalyzer(provider)
        # Ensure ffmpeg is not found
        analyzer._ffmpeg = None
        final_file = FinalFile(path=tmp_path / "video.mp4", size=1000)
        result = analyzer.analyze(final_file, _opts(ai_transcribe=True))
        assert result.transcription is None

    def test_transcribe_with_mocked_ffmpeg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess
        import shutil

        provider = _FakeAIProvider("Hello transcript")
        analyzer = ContentAnalyzer(provider)

        # Create a fake video file
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video data")

        # Mock ffmpeg to create the audio file
        def fake_run(cmd: list, **kwargs: object) -> object:
            # Create the audio file that ffmpeg would create
            audio_path = video_path.with_suffix(".audio.wav")
            audio_path.write_bytes(b"fake audio data")
            return MagicMock(returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)
        analyzer._ffmpeg = "/usr/bin/ffmpeg"

        final_file = FinalFile(path=video_path, size=1000)
        result = analyzer.analyze(final_file, _opts(ai_transcribe=True))
        assert result.transcription == "Hello transcript"

    def test_summarize_without_transcription_skipped(self, tmp_path: Path) -> None:
        provider = _FakeAIProvider("Summary text")
        analyzer = ContentAnalyzer(provider)
        final_file = FinalFile(path=tmp_path / "video.mp4", size=1000)
        result = analyzer.analyze(final_file, _opts(ai_summarize=True))
        # Without transcription, summarize should be skipped
        assert result.summary is None

    def test_thumbnails_no_ffmpeg_returns_empty(self, tmp_path: Path) -> None:
        provider = _FakeAIProvider()
        analyzer = ContentAnalyzer(provider)
        analyzer._ffmpeg = None
        final_file = FinalFile(path=tmp_path / "video.mp4", size=1000)
        result = analyzer.analyze(final_file, _opts(ai_thumbnails=True))
        assert result.thumbnails == []


class TestContentAnalyzerIntegration:
    def test_full_analysis_flow(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        provider = _FakeAIProvider("Full transcript here")
        analyzer = ContentAnalyzer(provider)

        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video data")

        # Mock ffmpeg for audio extraction and frame extraction
        call_count = 0
        def fake_run(cmd: list, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if "audio.wav" in " ".join(str(c) for c in cmd):
                video_path.with_suffix(".audio.wav").write_bytes(b"audio")
            elif "frame_" in " ".join(str(c) for c in cmd):
                # Create thumbnail frames
                thumb_dir = video_path.parent / "video_thumbnails"
                thumb_dir.mkdir(exist_ok=True)
                for i in range(3):
                    (thumb_dir / f"frame_{i:03d}.jpg").write_bytes(b"jpg")
            return MagicMock(returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)
        analyzer._ffmpeg = "/usr/bin/ffmpeg"

        final_file = FinalFile(path=video_path, size=1000)
        opts = _opts(ai_analyze=True, ai_transcribe=True, ai_summarize=True, ai_thumbnails=True)
        result = analyzer.analyze(final_file, opts)

        assert result.transcription == "Full transcript here"
        assert result.summary is not None
        assert len(result.thumbnails) == 3
