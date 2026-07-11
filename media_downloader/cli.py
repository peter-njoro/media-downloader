"""Command-line interface for the media downloader."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from media_downloader.models import Best, DownloadOptions, FormatId, Height, QualitySpec, Worst
from media_downloader.orchestrator import create_orchestrator
from media_downloader.progress import ConsoleProgressReporter


@click.command()
@click.argument("url")
@click.option("--quality", type=click.Choice(["best", "worst"]), default="best")
@click.option("--audio-only", is_flag=True)
@click.option("--audio-format")
@click.option("--output", "output_template", default="%(title)s.%(ext)s")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.option("--rate-limit", type=int)
@click.option("--retries", type=int, default=3)
@click.option("--resume/--no-resume", default=True)
@click.option("--concurrent-fragments", type=int, default=1)
@click.option("--js", is_flag=True, help="Use a headless browser to render JavaScript before extracting media")
def main(url: str, quality: str, audio_only: bool, audio_format: Optional[str], output_template: str, output_dir: Path, rate_limit: Optional[int], retries: int, resume: bool, concurrent_fragments: int, js: bool) -> None:
    opts = DownloadOptions(
        quality=_parse_quality(quality),
        audio_only=audio_only,
        audio_format=audio_format,
        output_template=output_template,
        output_dir=output_dir,
        rate_limit=rate_limit,
        retries=retries,
        resume=resume,
        concurrent_fragments=concurrent_fragments,
        js_render=js,
    )
    try:
        result = create_orchestrator().download(url, opts, progress_reporter=ConsoleProgressReporter())
    except Exception as exc:  # pragma: no cover - simple CLI wrapper
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(result.final_path)


def _parse_quality(value: str) -> QualitySpec:
    if value == "best":
        return Best()
    if value == "worst":
        return Worst()
    return Best()


if __name__ == "__main__":
    main()
