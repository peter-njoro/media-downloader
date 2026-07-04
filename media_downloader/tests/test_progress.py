"""
Unit tests for media_downloader/progress.py

Covers:
  - ProgressReporter Protocol structural checking
  - ConsoleProgressReporter output format (stderr writes)
  - ConsoleProgressReporter with known and unknown total_size
  - ConsoleProgressReporter.finish() writes a newline
  - NullProgressReporter does nothing
"""

from __future__ import annotations

import io
import sys
from typing import Optional

import pytest

from media_downloader.progress import (
    ConsoleProgressReporter,
    NullProgressReporter,
    ProgressReporter,
    _format_bytes,
    _format_speed,
)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProgressReporterProtocol:
    """Verify that concrete classes satisfy the ProgressReporter protocol."""

    def test_console_reporter_is_progress_reporter(self) -> None:
        assert isinstance(ConsoleProgressReporter(), ProgressReporter)

    def test_null_reporter_is_progress_reporter(self) -> None:
        assert isinstance(NullProgressReporter(), ProgressReporter)

    def test_custom_callable_satisfies_protocol(self) -> None:
        """Any object with an on_progress method satisfies the protocol."""

        class MyReporter:
            def on_progress(self, bytes_written: int, total_size: Optional[int]) -> None:
                pass

        assert isinstance(MyReporter(), ProgressReporter)

    def test_object_without_on_progress_does_not_satisfy_protocol(self) -> None:
        class BadReporter:
            pass

        assert not isinstance(BadReporter(), ProgressReporter)


# ---------------------------------------------------------------------------
# _format_bytes helper
# ---------------------------------------------------------------------------


class TestFormatBytes:
    def test_bytes_under_1024(self) -> None:
        assert _format_bytes(512) == "512.0 B"

    def test_kilobytes(self) -> None:
        result = _format_bytes(1024)
        assert "KB" in result

    def test_megabytes(self) -> None:
        result = _format_bytes(1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self) -> None:
        result = _format_bytes(1024 ** 3)
        assert "GB" in result

    def test_zero_bytes(self) -> None:
        result = _format_bytes(0)
        assert "B" in result


# ---------------------------------------------------------------------------
# _format_speed helper
# ---------------------------------------------------------------------------


class TestFormatSpeed:
    def test_bytes_per_second(self) -> None:
        result = _format_speed(500.0)
        assert "B/s" in result

    def test_kilobytes_per_second(self) -> None:
        result = _format_speed(2048.0)
        assert "KB/s" in result

    def test_megabytes_per_second(self) -> None:
        result = _format_speed(2.0 * 1024 * 1024)
        assert "MB/s" in result


# ---------------------------------------------------------------------------
# ConsoleProgressReporter — output content
# ---------------------------------------------------------------------------


class TestConsoleProgressReporter:
    """Test that ConsoleProgressReporter writes expected content to stderr."""

    def _capture(self, reporter: ConsoleProgressReporter, bytes_written: int, total_size: Optional[int]) -> str:
        """Call on_progress and return what was written to stderr."""
        buf = io.StringIO()
        original = sys.stderr
        sys.stderr = buf
        try:
            reporter.on_progress(bytes_written, total_size)
        finally:
            sys.stderr = original
        return buf.getvalue()

    def test_known_size_contains_percentage(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 5 * 1024 * 1024, 10 * 1024 * 1024)
        assert "50" in output  # 50%

    def test_known_size_contains_carriage_return(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 1024, 10 * 1024)
        assert output.startswith("\r")

    def test_known_size_contains_bar_characters(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 3000, 10000)
        assert "[" in output and "]" in output

    def test_known_size_contains_byte_counts(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 1024, 2048)
        # Both written and total should appear in some human-readable form
        assert "B" in output or "KB" in output

    def test_unknown_size_does_not_show_percentage(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 1024, None)
        assert "%" not in output

    def test_unknown_size_shows_bytes_downloaded(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 1024, None)
        assert "downloaded" in output.lower() or "B" in output

    def test_unknown_size_starts_with_carriage_return(self) -> None:
        reporter = ConsoleProgressReporter()
        output = self._capture(reporter, 512, None)
        assert output.startswith("\r")

    def test_finish_writes_newline(self) -> None:
        reporter = ConsoleProgressReporter()
        # First emit one progress event
        self._capture(reporter, 1024, 2048)
        # Then capture finish
        buf = io.StringIO()
        original = sys.stderr
        sys.stderr = buf
        try:
            reporter.finish()
        finally:
            sys.stderr = original
        assert buf.getvalue() == "\n"

    def test_multiple_calls_work(self) -> None:
        """on_progress can be called repeatedly without error."""
        reporter = ConsoleProgressReporter()
        for i in range(1, 6):
            self._capture(reporter, i * 1024, 5 * 1024)

    def test_zero_total_size_does_not_crash(self) -> None:
        """total_size=0 edge case should not raise ZeroDivisionError."""
        reporter = ConsoleProgressReporter()
        # total_size=0 is unusual but should not crash
        try:
            self._capture(reporter, 0, 0)
        except ZeroDivisionError:
            pytest.fail("on_progress raised ZeroDivisionError with total_size=0")

    def test_100_percent_completion(self) -> None:
        reporter = ConsoleProgressReporter()
        total = 10 * 1024 * 1024
        output = self._capture(reporter, total, total)
        assert "100" in output


# ---------------------------------------------------------------------------
# NullProgressReporter
# ---------------------------------------------------------------------------


class TestNullProgressReporter:
    def test_on_progress_does_not_write_to_stderr(self) -> None:
        reporter = NullProgressReporter()
        buf = io.StringIO()
        original = sys.stderr
        sys.stderr = buf
        try:
            reporter.on_progress(1024, 10240)
        finally:
            sys.stderr = original
        assert buf.getvalue() == ""

    def test_on_progress_unknown_size_does_not_write(self) -> None:
        reporter = NullProgressReporter()
        buf = io.StringIO()
        original = sys.stderr
        sys.stderr = buf
        try:
            reporter.on_progress(1024, None)
        finally:
            sys.stderr = original
        assert buf.getvalue() == ""

    def test_on_progress_returns_none(self) -> None:
        reporter = NullProgressReporter()
        result = reporter.on_progress(0, None)
        assert result is None

    def test_multiple_calls_are_silent(self) -> None:
        reporter = NullProgressReporter()
        buf = io.StringIO()
        original = sys.stderr
        sys.stderr = buf
        try:
            for i in range(10):
                reporter.on_progress(i * 100, 1000)
        finally:
            sys.stderr = original
        assert buf.getvalue() == ""
