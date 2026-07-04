"""
Output Path Resolver — Component 7.

Converts a yt-dlp-style output template (e.g. ``%(title)s.%(ext)s``) and a
``MediaManifest`` into a concrete, sanitised, collision-free ``Path``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from media_downloader.models import MediaManifest

# ---------------------------------------------------------------------------
# Characters that are illegal in filenames on Windows or POSIX
# (we also replace ASCII control characters 0x00-0x1F)
# ---------------------------------------------------------------------------
_ILLEGAL_CHARS: re.Pattern[str] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Maximum UTF-8 byte length for a filename (common FS limit)
_MAX_FILENAME_BYTES: int = 255


class OutputPathResolver:
    """Resolves an output template + manifest into a safe, unique file path."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        template: str,
        manifest: MediaManifest,
        output_dir: Path,
    ) -> Path:
        """Return a concrete, sanitised, collision-free path.

        Parameters
        ----------
        template:
            A ``%(key)s``-style format string.  Supported keys:
            ``id``, ``title``, ``uploader``, ``duration``, ``ext``.
        manifest:
            The :class:`~media_downloader.models.MediaManifest` whose
            metadata is used for substitution.
        output_dir:
            Base directory in which the file will be placed.

        Returns
        -------
        Path
            An absolute (or relative-to-cwd) path that does **not** yet exist
            on the filesystem.
        """
        raw_name = self._substitute(template, manifest)
        safe_name = self._sanitize(raw_name)
        return self._avoid_collision(output_dir, safe_name)

    # ------------------------------------------------------------------
    # Template substitution
    # ------------------------------------------------------------------

    def _substitute(self, template: str, manifest: MediaManifest) -> str:
        """Replace ``%(key)s`` placeholders with manifest field values."""
        # Derive ``ext`` from the first format's container field.
        ext: str = manifest.formats[0].container if manifest.formats else ""

        replacements: dict[str, str] = {
            "id": manifest.id or "",
            "title": manifest.title or "",
            "uploader": manifest.uploader or "",
            "duration": str(manifest.duration) if manifest.duration is not None else "",
            "ext": ext,
        }

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return replacements.get(key, match.group(0))  # leave unknown keys as-is

        return re.sub(r"%\((\w+)\)s", _replace, template)

    # ------------------------------------------------------------------
    # Filename sanitisation
    # ------------------------------------------------------------------

    def _sanitize(self, filename: str) -> str:
        """Return a filesystem-safe version of *filename*.

        Steps applied in order:
        1. Replace illegal characters (``< > : " / \\ | ? *`` and control
           chars 0x00-0x1F) with ``_``.
        2. Strip leading/trailing dots and spaces.
        3. Truncate so the UTF-8 encoded result is at most 255 bytes,
           preserving the file extension if present.
        4. Fall back to ``_`` if the result is empty after sanitisation.
        """
        # Step 1 — replace illegal characters
        sanitized = _ILLEGAL_CHARS.sub("_", filename)

        # Step 2 — strip leading/trailing dots and spaces
        sanitized = sanitized.strip(". ")

        # Step 3 — truncate to 255 UTF-8 bytes while keeping the extension
        sanitized = self._truncate(sanitized)

        # Step 4 — guard against empty result
        if not sanitized:
            sanitized = "_"

        return sanitized

    @staticmethod
    def _truncate(filename: str, max_bytes: int = _MAX_FILENAME_BYTES) -> str:
        """Truncate *filename* so its UTF-8 encoding fits within *max_bytes*.

        The file extension (everything after the last ``.``) is preserved
        when possible.
        """
        encoded = filename.encode("utf-8")
        if len(encoded) <= max_bytes:
            return filename

        # Split into stem and extension (extension includes the leading dot)
        dot_idx = filename.rfind(".")
        if dot_idx > 0:
            stem = filename[:dot_idx]
            ext = filename[dot_idx:]  # e.g. ".mp4"
        else:
            stem = filename
            ext = ""

        ext_bytes = ext.encode("utf-8")
        if len(ext_bytes) >= max_bytes:
            # Extension alone is already too long; truncate the whole thing
            result = encoded[:max_bytes].decode("utf-8", errors="ignore")
            return result.rstrip()  # avoid trailing partial multi-byte sequences

        stem_budget = max_bytes - len(ext_bytes)
        # Truncate stem bytes and decode safely (avoid splitting multi-byte chars)
        truncated_stem = stem.encode("utf-8")[:stem_budget].decode(
            "utf-8", errors="ignore"
        )
        return truncated_stem + ext

    # ------------------------------------------------------------------
    # Collision avoidance
    # ------------------------------------------------------------------

    @staticmethod
    def _avoid_collision(output_dir: Path, filename: str) -> Path:
        """Return ``output_dir / filename``, appending ``(n)`` if it exists.

        Tries ``filename``, then ``<stem> (1)<ext>``, ``<stem> (2)<ext>``, …
        """
        candidate = output_dir / filename
        if not candidate.exists():
            return candidate

        # Split into stem and suffix (suffix includes the leading dot)
        p = Path(filename)
        stem = p.stem
        suffix = p.suffix  # e.g. ".mp4" or "" if no extension

        counter = 1
        while True:
            new_name = f"{stem} ({counter}){suffix}"
            candidate = output_dir / new_name
            if not candidate.exists():
                return candidate
            counter += 1
