from __future__ import annotations

from pathlib import Path

from media_downloader.models import DownloadedFile, DownloadedFiles
from media_downloader.post_processor import PostProcessor


def test_process_uses_requested_output_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("media_downloader.post_processor.shutil.which", lambda _: "/usr/bin/ffmpeg")

    input_path = tmp_path / "input.png"
    input_path.write_bytes(b"png")
    output_path = tmp_path / "final.png"

    processor = PostProcessor()
    files = DownloadedFiles(files=[DownloadedFile(path=input_path, size=1)], requires_mux=False)

    def fake_run_ffmpeg(command: list[str]) -> None:
        Path(command[-1]).write_bytes(b"done")

    monkeypatch.setattr(processor, "_run_ffmpeg", fake_run_ffmpeg)

    final_file = processor.process(files, output_path=output_path)

    assert final_file.path == output_path
    assert output_path.exists()
    assert not (tmp_path / "input.final").exists()
