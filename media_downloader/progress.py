"""
Progress reporting for active downloads.

Defines the ProgressReporter protocol and two concrete implementations:
  - ConsoleProgressReporter — writes a live progress bar to stderr
  - NullProgressReporter    — silent no-op (useful for tests / library use)
"""

from __future__ import annotations

import sys
import time
from typing import Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # Python < 3.8 fallback (shouldn't be needed, but safe)
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ProgressReporter(Protocol):
    """Interface for objects that receive download progress events."""

    def on_progress(
        self,
        bytes_written: int,
        total_size: Optional[int],
    ) -> None:
        """Called after each chunk is written to disk.

        Args:
            bytes_written: Total bytes written so far (including resume offset).
            total_size:    Full content length in bytes, or ``None`` if unknown.
        """
        ...


# ---------------------------------------------------------------------------
# ConsoleProgressReporter
# ---------------------------------------------------------------------------

_BAR_WIDTH = 30  # characters in the filled bar


def _format_bytes(n: int) -> str:
    """Human-readable byte size (e.g. '1.4 MB')."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def _format_speed(bps: float) -> str:
    """Human-readable throughput string (e.g. '2.3 MB/s')."""
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024:
            return f"{bps:.1f} {unit}"
        bps /= 1024
    return f"{bps:.1f} GB/s"


class ConsoleProgressReporter:
    """Prints a carriage-return–overwritten progress bar to stderr.

    Example output (known size)::

        Downloading: [===========         ]  55%  (5.5 MB/10.0 MB)  1.2 MB/s

    Example output (unknown size)::

        Downloading:  5.5 MB downloaded  1.2 MB/s
    """

    def __init__(self) -> None:
        self._start_time: Optional[float] = None
        self._last_bytes: int = 0
        self._last_time: Optional[float] = None

    def on_progress(
        self,
        bytes_written: int,
        total_size: Optional[int],
    ) -> None:
        now = time.monotonic()

        if self._start_time is None:
            self._start_time = now
            self._last_bytes = bytes_written
            self._last_time = now

        # Compute instantaneous speed over the last interval.
        dt = now - (self._last_time or now)
        if dt > 0:
            speed = (bytes_written - self._last_bytes) / dt
        else:
            speed = 0.0

        self._last_bytes = bytes_written
        self._last_time = now

        if total_size is not None and total_size > 0:
            pct = bytes_written / total_size
            filled = int(_BAR_WIDTH * pct)
            bar = "=" * filled + " " * (_BAR_WIDTH - filled)
            line = (
                f"\rDownloading: [{bar}] {pct * 100:5.1f}%"
                f"  ({_format_bytes(bytes_written)}/{_format_bytes(total_size)})"
                f"  {_format_speed(speed)}"
            )
        else:
            line = (
                f"\rDownloading:  {_format_bytes(bytes_written)} downloaded"
                f"  {_format_speed(speed)}"
            )

        sys.stderr.write(line)
        sys.stderr.flush()

    def finish(self) -> None:
        """Write a final newline so the next stderr/stdout line is clean."""
        sys.stderr.write("\n")
        sys.stderr.flush()


# ---------------------------------------------------------------------------
# NullProgressReporter
# ---------------------------------------------------------------------------


class NullProgressReporter:
    """A no-op progress reporter for testing and library / silent use."""

    def on_progress(
        self,
        bytes_written: int,
        total_size: Optional[int],
    ) -> None:
        pass
