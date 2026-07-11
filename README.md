# Media Downloader

Media Downloader is a small Python library and CLI for downloading media from direct URLs and web pages. It provides a pipeline for resolving a media source, selecting an appropriate stream, downloading it, and optionally post-processing the result.

## What it does

- Supports direct media URLs through a generic HTTP extractor
- Supports static web pages through a built-in HTML scraper that discovers media from common tags and links
- Supports JavaScript-rendered pages via an optional Playwright-based extractor that can discover dynamically loaded media
- Selects a suitable video, audio, or combined stream based on quality preferences
- Downloads files with optional resume support and progress reporting
- Offers a simple command-line interface and a reusable Python API

## How it works

1. A URL is passed to the extractor registry.
2. The matching extractor builds a media manifest describing available formats.
   - Direct media URLs are handled by the generic extractor.
   - Static HTML pages are handled by the web scraper, which looks for video/audio tags, source elements, image links, and common metadata hints.
   - JavaScript-rendered pages (opt-in via `--js`) are handled by the Playwright-based extractor, which renders the page in a headless browser, queries the live DOM for media elements, and intercepts network requests to catch dynamically loaded media.
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

Direct image example with an explicit output directory:

```bash
media-dl https://images.pexels.com/photos/37636725/pexels-photo-37636725.jpeg --quality best --output "%(title)s.%(ext)s" --output-dir ./downloads
```

Example for a simple HTML page containing embedded media:

```bash
media-dl https://example.com/page-with-video --quality best --output "%(title)s.%(ext)s"
```

### JavaScript-rendered pages

For pages where media is loaded dynamically by JavaScript (single-page apps, players that fetch streams via AJAX), use the `--js` flag:

```bash
media-dl --js https://example.com/spa-page --quality best --output "%(title)s.%(ext)s"
```

This launches a headless Chromium browser via Playwright, waits for the page to finish rendering, then discovers media through two strategies:

- **DOM inspection** — queries the rendered HTML for `<video>`, `<audio>`, `<source>`, and `<img>` elements
- **Network interception** — captures HTTP responses whose URLs match known media extensions (`.mp4`, `.m3u8`, `.mpd`, `.ts`, etc.), catching media loaded via XHR/fetch that never appears in the DOM

> **Note:** The `--js` flag requires Playwright browser binaries. If you haven't installed them yet, run:
> ```bash
> playwright install
> ```

### Web scraper notes

- The default web scraper targets static, non-JavaScript pages.
- It discovers media from common HTML patterns such as `video`, `audio`, `source`, `img`, anchor links, and metadata like `og:image`.
- Use `--js` for JavaScript-rendered pages where the static scraper finds nothing.

## Python API

```python
from media_downloader import DownloadOptions, Orchestrator, create_orchestrator

orchestrator = create_orchestrator()
opts = DownloadOptions(output_template="%(title)s.%(ext)s")
result = orchestrator.download("https://example.com/video.mp4", opts)
print(result.final_path)
```

For JavaScript-rendered pages:

```python
opts = DownloadOptions(js_render=True, output_template="%(title)s.%(ext)s")
result = orchestrator.download("https://example.com/spa-page", opts)
```

## Notes

This project was created with the help of Kiro by AWS and GitHub Copilot.
