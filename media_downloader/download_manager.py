"""Download Manager for the media downloader."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from media_downloader.models import (
    DiskFull,
    DownloadError,
    DownloadedFile,
    DownloadedFiles,
    HTTPError,
    NetworkError,
    ResumeState,
    SelectedFormats,
)
from media_downloader.progress import ProgressReporter
from media_downloader.resume import ResumeStateStore


class DownloadManager:
    """Downloads selected streams to disk with optional resume support."""

    def __init__(self, resume_store: Optional[ResumeStateStore] = None) -> None:
        self._resume_store = resume_store or ResumeStateStore(Path(".media_dl_resume"))
        self._cancelled = False

    def download(
        self,
        selected: SelectedFormats,
        dest_dir: Path,
        opts,
        on_progress: Optional[ProgressReporter] = None,
    ) -> DownloadedFiles:
        dest_dir.mkdir(parents=True, exist_ok=True)
        files: list[DownloadedFile] = []
        for stream in [selected.video, selected.audio]:
            if stream is None:
                continue
            path = dest_dir / f"{self._safe_name(stream.format_id)}.{stream.container}"
            self._download_stream(stream.url, path, opts, on_progress)
            files.append(DownloadedFile(path=path, size=path.stat().st_size))
        return DownloadedFiles(files=files, requires_mux=selected.requires_mux)

    def cancel(self) -> None:
        self._cancelled = True

    def _download_stream(
        self,
        url: str,
        dest_path: Path,
        opts,
        on_progress: Optional[ProgressReporter],
    ) -> None:
        temp_path = dest_path.with_suffix(dest_path.suffix + ".part")
        resume_state = self._resume_store.get(url) if opts.resume else None
        offset = resume_state.bytes_written if resume_state is not None else 0

        headers = {}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers, follow_redirects=True)
                if response.status_code not in {200, 206}:
                    raise HTTPError(url, response.status_code)
                mode = "ab" if offset > 0 else "wb"
                with temp_path.open(mode, encoding="utf-8") as handle:
                    handle.close()
                with temp_path.open("ab" if offset > 0 else "wb") as handle:
                    written = offset
                    for chunk in response.iter_bytes(chunk_size=8192):
                        if self._cancelled:
                            break
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        self._resume_store.update(url, written, response.headers.get("content-length"))
                        if on_progress is not None:
                            on_progress.on_progress(written, None)
                        if opts.rate_limit:
                            time.sleep(len(chunk) / opts.rate_limit)
        except httpx.HTTPError as exc:
            raise NetworkError(url, str(exc)) from exc
        except OSError as exc:
            raise DiskFull(dest_path) from exc

        if self._cancelled:
            return

        temp_path.replace(dest_path)
        self._resume_store.clear(url)

    @staticmethod
    def _safe_name(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
