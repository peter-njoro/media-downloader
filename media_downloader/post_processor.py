"""FFmpeg-based post-processing bridge."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from media_downloader.models import (
    FinalFile,
    ProcessingError,
    ProcessingFailed,
    PostProcessOptions,
    DownloadedFiles,
)


class PostProcessor:
    """Muxes or converts downloaded files to a final output artifact."""

    def __init__(self) -> None:
        self._ffmpeg = shutil.which("ffmpeg")
        if self._ffmpeg is None and self._requires_ffmpeg():
            raise RuntimeError("ffmpeg not found on PATH")

    # Image containers that should be passed through without ffmpeg
    _IMAGE_CONTAINERS = frozenset({
        "jpg", "jpeg", "png", "gif", "webp", "bmp",
        "avif", "heic", "heif", "tif", "tiff",
    })

    def process(
        self,
        files: DownloadedFiles,
        opts: Optional[PostProcessOptions] = None,
        output_path: Optional[Path] = None,
    ) -> FinalFile:
        opts = opts or PostProcessOptions()
        if not files.files:
            raise ProcessingError("No downloaded files to process")

        source = files.files[0]
        suffix = source.path.suffix.lower().lstrip(".")

        # Unknown binary blob — ffmpeg can't help here
        if suffix == "bin":
            raise ProcessingError(
                f"Cannot process '{source.path.name}': file type is unknown (container reported as 'bin'). "
                "The URL may not point to a recognised media file."
            )

        # Images don't need transcoding — just rename to the final path
        if suffix in self._IMAGE_CONTAINERS:
            output_path = output_path or source.path
            if output_path != source.path:
                source.path.replace(output_path)
            return FinalFile(path=output_path, size=output_path.stat().st_size)

        if files.requires_mux and self._ffmpeg is None:
            raise RuntimeError("ffmpeg not found on PATH")
        output_path = output_path or self._default_output_path(source.path)
        if files.requires_mux:
            self._run_ffmpeg([self._ffmpeg, "-y", "-i", str(source.path), "-i", str(files.files[1].path), "-c", "copy", str(output_path)])
        else:
            self._run_ffmpeg([self._ffmpeg, "-y", "-i", str(source.path), str(output_path)])
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ProcessingFailed("output was not created")
        for downloaded_file in files.files:
            if downloaded_file.path.exists():
                downloaded_file.path.unlink()
        return FinalFile(path=output_path, size=output_path.stat().st_size)

    def _run_ffmpeg(self, command: list[str]) -> None:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ProcessingFailed(completed.stderr or completed.stdout or "ffmpeg failed")

    @staticmethod
    def _default_output_path(source_path: Path) -> Path:
        return source_path.with_suffix(".final")

    @staticmethod
    def _requires_ffmpeg() -> bool:
        return True
