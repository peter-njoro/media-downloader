# Media Downloader

Media Downloader is a small Python library and CLI for downloading media from direct URLs. It provides a simple pipeline for resolving a media URL, selecting an appropriate stream, downloading it, and optionally post-processing the result.

## What it does

- Supports direct media URLs through a generic HTTP extractor
- Selects a suitable video, audio, or combined stream based on quality preferences
- Downloads files with optional resume support and progress reporting
- Offers a simple command-line interface and a reusable Python API

## How it works

1. A URL is passed to the extractor registry.
2. The matching extractor builds a media manifest describing available formats.
3. The format selector chooses the best stream(s) for the requested quality options.
4. The download manager fetches the selected stream(s) to disk, with resume support.
5. The post-processor can mux or convert the downloaded files into a final output.
6. The output path resolver creates a safe, unique destination path.

## CLI usage

Install the package and run:

```bash
media-dl <url> [options]
```

Example:

```bash
media-dl https://example.com/video.mp4 --quality best --output "%(title)s.%(ext)s"
```

## Python API

```python
from media_downloader import DownloadOptions, Orchestrator, create_orchestrator

orchestrator = create_orchestrator()
opts = DownloadOptions(output_template="%(title)s.%(ext)s")
result = orchestrator.download("https://example.com/video.mp4", opts)
print(result.final_path)
```

## Notes

This project was created with the help of Kiro by AWS and GitHub Copilot.
