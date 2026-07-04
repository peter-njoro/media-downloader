"""
Resume state persistence for interrupted downloads.

ResumeStateStore persists ResumeState as JSON files in a .media_dl_resume/
cache directory, keyed by the SHA-256 hash of the download URL.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from media_downloader.models import ResumeState


class ResumeStateStore:
    """Persists and retrieves resume state for interruptible downloads.

    State files are stored as JSON in a .media_dl_resume/ directory,
    each file named by the SHA-256 hash of the corresponding URL.
    """

    def __init__(self, cache_dir: Path) -> None:
        """
        Args:
            cache_dir: Directory where resume state JSON files are stored.
                       Typically ``<output_dir>/.media_dl_resume/``.
        """
        self._cache_dir = cache_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, url: str) -> str:
        """Return the SHA-256 hex digest of *url* for use as a filename."""
        return hashlib.sha256(url.encode()).hexdigest()

    def _state_path(self, url: str) -> Path:
        return self._cache_dir / f"{self._key(url)}.json"

    def _ensure_cache_dir(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str) -> Optional[ResumeState]:
        """Load persisted resume state for *url*.

        Returns:
            A :class:`ResumeState` if a valid state file exists, otherwise
            ``None``.  Returns ``None`` on JSON decode errors rather than
            raising, so a corrupt cache file simply causes the download to
            restart from the beginning.
        """
        path = self._state_path(url)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        try:
            return ResumeState(
                url=data["url"],
                temp_path=Path(data["temp_path"]),
                bytes_written=int(data["bytes_written"]),
                total_size=data.get("total_size"),  # Optional[int]
                etag=data.get("etag"),
                last_modified=data.get("last_modified"),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def update(
        self,
        url: str,
        bytes_written: int,
        total_size: Optional[int] = None,
    ) -> None:
        """Persist (or overwrite) resume state for *url*.

        Args:
            url: The download URL being tracked.
            bytes_written: Number of bytes already written to the temp file.
            total_size: Content-Length of the full resource, if known.
        """
        self._ensure_cache_dir()
        path = self._state_path(url)
        # Derive the expected temp path from the URL hash so callers that
        # only know the URL can still reconstruct it.  The download manager
        # is free to store the real temp path via a full ResumeState write,
        # but for incremental chunk updates this default is sufficient.
        data: dict = {
            "url": url,
            "temp_path": str(self._cache_dir.parent / f"{self._key(url)}.part"),
            "bytes_written": bytes_written,
            "total_size": total_size,
            "etag": None,
            "last_modified": None,
        }
        # Preserve existing etag / last_modified / temp_path if a state
        # file already exists so we don't clobber those fields.
        existing = self.get(url)
        if existing is not None:
            data["temp_path"] = str(existing.temp_path)
            data["etag"] = existing.etag
            data["last_modified"] = existing.last_modified

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear(self, url: str) -> None:
        """Delete the resume state file for *url*, if it exists."""
        path = self._state_path(url)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
