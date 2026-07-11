"""Command-line interface for the media downloader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import click

from media_downloader.models import (
    AIConfig,
    AIRecommended,
    Best,
    DownloadOptions,
    FormatId,
    Height,
    QualitySpec,
    Worst,
)
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
@click.option("--ai-extract", is_flag=True, help="Use AI to reverse-engineer obfuscated media URLs")
@click.option("--ai-quality", is_flag=True, help="Use AI to recommend optimal format for content type")
@click.option("--ai-analyze", is_flag=True, help="Run AI content analysis after download")
@click.option("--ai-transcribe", is_flag=True, help="Generate SRT captions via AI speech-to-text")
@click.option("--ai-summarize", is_flag=True, help="Generate a text summary via AI")
@click.option("--ai-thumbnails", is_flag=True, help="Generate representative thumbnails via AI")
@click.option("--ai-provider", type=click.Choice(["openai", "anthropic", "ollama"]), default=None, help="AI provider to use")
@click.option("--ai-model", default=None, help="AI model name (provider-specific)")
@click.option("--ai-api-key", default=None, help="AI API key (or set via env var)")
def main(
    url: str,
    quality: str,
    audio_only: bool,
    audio_format: Optional[str],
    output_template: str,
    output_dir: Path,
    rate_limit: Optional[int],
    retries: int,
    resume: bool,
    concurrent_fragments: int,
    js: bool,
    ai_extract: bool,
    ai_quality: bool,
    ai_analyze: bool,
    ai_transcribe: bool,
    ai_summarize: bool,
    ai_thumbnails: bool,
    ai_provider: Optional[str],
    ai_model: Optional[str],
    ai_api_key: Optional[str],
) -> None:
    # Build quality spec
    q: QualitySpec = _parse_quality(quality)
    if ai_quality:
        q = AIRecommended()

    opts = DownloadOptions(
        quality=q,
        audio_only=audio_only,
        audio_format=audio_format,
        output_template=output_template,
        output_dir=output_dir,
        rate_limit=rate_limit,
        retries=retries,
        resume=resume,
        concurrent_fragments=concurrent_fragments,
        js_render=js,
        ai_extract=ai_extract,
        ai_quality=ai_quality,
        ai_analyze=ai_analyze or ai_transcribe or ai_summarize or ai_thumbnails,
        ai_transcribe=ai_transcribe,
        ai_summarize=ai_summarize,
        ai_thumbnails=ai_thumbnails,
    )

    # Build AI config if any AI flag is used
    ai_config: Optional[AIConfig] = None
    if opts.ai_analyze or opts.ai_extract or ai_quality:
        provider_name = ai_provider or _detect_provider()
        if provider_name is None:
            click.echo(
                "AI features require a provider. Set --ai-provider or "
                "set OPENAI_API_KEY / ANTHROPIC_API_KEY, or install Ollama.",
                err=True,
            )
            raise SystemExit(1)
        ai_config = AIConfig(
            provider=provider_name,
            model=ai_model,
            api_key=ai_api_key,
        )

    try:
        result = create_orchestrator(ai_config=ai_config).download(
            url, opts, progress_reporter=ConsoleProgressReporter()
        )
    except Exception as exc:  # pragma: no cover - simple CLI wrapper
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(result.final_path)

    # Print analysis results if available
    if result.analysis:
        if result.analysis.transcription:
            srt_path = result.final_path.with_suffix(".srt")
            srt_path.write_text(result.analysis.transcription, encoding="utf-8")
            click.echo(f"Transcription saved to: {srt_path}", err=True)
        if result.analysis.summary:
            click.echo(f"\n--- Summary ---\n{result.analysis.summary}", err=True)
        if result.analysis.thumbnails:
            for thumb in result.analysis.thumbnails:
                click.echo(f"Thumbnail: {thumb}", err=True)


def _parse_quality(value: str) -> QualitySpec:
    if value == "best":
        return Best()
    if value == "worst":
        return Worst()
    return Best()


def _detect_provider() -> Optional[str]:
    """Auto-detect AI provider from environment variables."""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


if __name__ == "__main__":
    main()
