# Implementation Plan: Media Downloader

## Overview

Implement a Python CLI tool and reusable library for downloading video and audio from internet sources. The implementation follows the pipeline: URL → Extractor Registry → Format Selector → Download Manager → Post-Processor → Output Path Resolver, coordinated by a central Download Orchestrator. All components are implemented as clean Python modules with type hints, exposed both as a CLI and as a programmatic API.

## Tasks

- [x] 1. Project setup and core type definitions
  - Create the package directory structure: `media_downloader/`, `media_downloader/extractors/`, `media_downloader/tests/`
  - Create `pyproject.toml` with dependencies: `httpx`, `click`, `pytest`, `hypothesis`, `ffmpeg-python` (pinned versions)
  - Create `media_downloader/__init__.py`, `media_downloader/py.typed` marker
  - Define all data models in `media_downloader/models.py`: `StreamType` enum, `Format`, `MediaManifest`, `DownloadOptions`, `QualitySpec`, `SelectedFormats`, `DownloadResult`, `ResumeState`, `DownloadedFile`, `DownloadedFiles`, `FinalFile`, and all error types (`DownloadError`, `ExtractionError`, `SelectionError`, `ProcessingError`)
  - Use `dataclasses` or `attrs` with `__slots__` for all models; use `typing.Optional`, `typing.List` throughout
  - _Requirements: all data models from design §Data Models_

- [ ] 2. Extractor Registry and Generic HTTP Extractor
  - [-] 2.1 Implement `ExtractorRegistry` in `media_downloader/registry.py`
    - `register(extractor: Extractor) -> None` — append to ordered list
    - `resolve(url: str) -> Optional[Extractor]` — return first extractor whose `can_handle` returns True, or None
    - `extractors` property returning current list
    - _Requirements: Component 2 — Extractor Registry_

  - [~] 2.2 Write property test for extractor registry resolution
    - **Property 7: Extractor Resolution Consistency** — for any resolved extractor `e`, `e.can_handle(url)` must be True
    - **Validates: Requirements Component 2, P7**

  - [-] 2.3 Implement `Extractor` abstract base class in `media_downloader/extractors/base.py`
    - Abstract methods `can_handle(url: str) -> bool` and `extract(url: str) -> Result[MediaManifest, ExtractionError]`
    - _Requirements: Component 3 — Extractor_

  - [~] 2.4 Implement `GenericHTTPExtractor` in `media_downloader/extractors/generic.py`
    - `can_handle`: returns True for any URL ending in a known media extension (`.mp4`, `.webm`, `.mkv`, `.m4a`, `.mp3`, `.ogg`)
    - `extract`: issues a HEAD request to get content-type/content-length, constructs a single-format `MediaManifest` from the URL itself
    - Use `httpx` for HTTP; handle network errors → `ExtractionError`
    - _Requirements: Component 3 — Generic HTTP Extractor_

  - [~] 2.5 Write unit tests for `GenericHTTPExtractor`
    - Test `can_handle` with media and non-media URLs
    - Test `extract` with mocked `httpx` responses
    - _Requirements: Component 3_

- [ ] 3. Format Selector
  - [x] 3.1 Implement `FormatSelector` in `media_downloader/format_selector.py`
    - `select(manifest: MediaManifest, opts: DownloadOptions) -> Result[SelectedFormats, SelectionError]`
    - Implement `quality_score(fmt: Format, opts: DownloadOptions) -> float` per Algorithm 5: Best → `height*10000 + vbr + abr`, Worst → negated score, Height(n) → `-abs(height - n)`
    - Implement `audio_score(fmt: Format) -> float` for audio-only selection
    - Handle `FormatId` direct selection, `audioOnly` mode, combined-stream preference, and video+audio mux path per Algorithm 2
    - _Requirements: Component 4 — Format Selector, Algorithm 2, Algorithm 5_

  - [~] 3.2 Write property test for mux consistency
    - **Property 2: Mux Consistency** — for all manifests and options, `select(m, opts).require_mux == (video is not None and audio is not None)`
    - **Validates: Requirements P2**

  - [~] 3.3 Write property test for idempotent format selection
    - **Property 6: Idempotent Format Selection** — calling `select(m, opts)` twice with the same inputs returns identical results
    - **Validates: Requirements P6**

  - [~] 3.4 Write unit tests for `FormatSelector`
    - Test each `QualitySpec` branch: Best, Worst, Height, FormatId
    - Test audioOnly mode
    - Test `NoSuitableFormatFound` error path
    - _Requirements: Component 4_

- [~] 4. Checkpoint — ensure data models and core selection logic are sound
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Download Manager
  - [-] 5.1 Implement `ResumeStateStore` in `media_downloader/resume.py`
    - Persist `ResumeState` as JSON files in a `.media_dl_resume/` cache directory (keyed by URL hash)
    - Methods: `get(url: str) -> Optional[ResumeState]`, `update(url: str, bytes_written: int) -> None`, `clear(url: str) -> None`
    - _Requirements: Component 5 — Resume State Store, Model 6_

  - [-] 5.2 Implement `ProgressReporter` in `media_downloader/progress.py`
    - Callable protocol: `on_progress(bytes_written: int, total_size: Optional[int]) -> None`
    - Default implementation prints a progress bar to stderr using carriage-return overwrite
    - _Requirements: Component 5 — Progress Reporter_

  - [~] 5.3 Implement `DownloadManager` in `media_downloader/download_manager.py`
    - `download(selected: SelectedFormats, dest_dir: Path, opts: DownloadOptions, on_progress: ProgressReporter) -> Result[DownloadedFiles, DownloadError]`
    - `cancel() -> None` — sets a cancellation flag checked in the chunk loop
    - Implement `_download_stream(url, dest_path, opts, on_progress)` per Algorithm 3:
      - Read resume offset from `ResumeStateStore` if `opts.resume` is True
      - Issue `Range: bytes=<offset>-` request via `httpx`
      - Write chunks to `<dest>.part` temp file, updating resume state each chunk
      - Respect `opts.rate_limit` (token-bucket sleep between chunks)
      - On completion: rename `.part` → final path, clear resume state
    - Handle HTTP 200/206 status codes; surface others as `DownloadError`
    - _Requirements: Component 5 — Download Manager, Algorithm 3_

  - [~] 5.4 Write property test for download completeness
    - **Property 3: Download Completeness** — if `download_stream` succeeds, the resulting file size equals the reported remote size
    - **Validates: Requirements P3**

  - [~] 5.5 Write property test for resume correctness
    - **Property 4: Resume Correctness** — if a `ResumeState` with `bytes_written=k` exists, the next download with `resume=True` issues a `Range: bytes=k-` request
    - **Validates: Requirements P4**

  - [~] 5.6 Write unit tests for `DownloadManager`
    - Test successful chunked download with mocked `httpx`
    - Test resume offset is read and applied
    - Test cancellation mid-download leaves `.part` file intact
    - Test disk-full error path
    - _Requirements: Component 5_

- [ ] 6. Post-Processor (FFmpeg bridge)
  - [~] 6.1 Implement `PostProcessor` in `media_downloader/post_processor.py`
    - `process(files: DownloadedFiles, opts: PostProcessOptions) -> Result[FinalFile, ProcessingError]`
    - Detect mux need: `files.requires_mux` → invoke FFmpeg via `subprocess` to stream-copy video+audio into output container
    - Audio conversion: if `opts.audio_format` is set, invoke FFmpeg to transcode to target codec/container
    - Validate output file exists and has non-zero size after processing
    - On success: delete intermediate downloaded files
    - On failure: preserve raw downloaded files; return `Err(ProcessingFailed(ffmpeg_stderr))`
    - Check FFmpeg availability on import; raise `RuntimeError` if not found and mux is required
    - _Requirements: Component 6 — Post-Processor_

  - [~] 6.2 Write unit tests for `PostProcessor`
    - Test mux detection logic
    - Test FFmpeg invocation arguments with mocked `subprocess`
    - Test failure path preserves raw files
    - _Requirements: Component 6_

- [ ] 7. Output Path Resolver
  - [-] 7.1 Implement `OutputPathResolver` in `media_downloader/output_resolver.py`
    - `resolve(template: str, manifest: MediaManifest) -> Path`
    - Substitute `%(key)s` template variables from manifest fields: `id`, `title`, `uploader`, `duration`, `ext` (from selected format container)
    - Sanitize filename: strip/replace characters illegal on Windows and POSIX (`< > : " / \ | ? *` and control chars); truncate to 255 bytes
    - Collision avoidance: if `<path>` exists, try `<stem> (1)<ext>`, `<stem> (2)<ext>`, etc.
    - _Requirements: Component 7 — Output Path Resolver_

  - [~] 7.2 Write property test for output path safety
    - **Property 8: Output Path Safety** — for any template and manifest, the resolved filename contains no illegal filesystem characters
    - **Validates: Requirements P8**

  - [~] 7.3 Write unit tests for `OutputPathResolver`
    - Test all template variables are substituted
    - Test illegal-character sanitization
    - Test collision avoidance increments index correctly
    - _Requirements: Component 7_

- [ ] 8. Download Orchestrator
  - [~] 8.1 Implement `Orchestrator` in `media_downloader/orchestrator.py`
    - `download(url: str, opts: DownloadOptions) -> Result[DownloadResult, DownloadError]`
    - `download_batch(urls: List[str], opts: DownloadOptions) -> List[Result[DownloadResult, DownloadError]]`
    - Implement Algorithm 1: resolve extractor → extract manifest → select formats → resolve output path → download → post-process
    - Retry extraction/download up to `opts.retries` times with exponential backoff for transient errors
    - Emit lifecycle events via optional `on_event` callback: `start`, `progress`, `complete`, `error`
    - On any failure: ensure no partial files remain in output directory
    - _Requirements: Component 1 — Download Orchestrator, Algorithm 1_

  - [~] 8.2 Write property test for no-partial-output guarantee
    - **Property 5: No Partial Output** — if `download()` returns an error, no file exists at the would-be `final_path` in the output directory
    - **Validates: Requirements P5**

  - [~] 8.3 Write unit tests for `Orchestrator`
    - Test happy path with all components mocked
    - Test each failure branch (no extractor, extraction failure, selection failure, download failure, processing failure)
    - Test retry logic respects `opts.retries`
    - _Requirements: Component 1_

- [~] 9. Checkpoint — ensure full pipeline integration is correct
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. CLI entry point
  - [~] 10.1 Implement CLI in `media_downloader/cli.py` using `click`
    - Command `media-dl <url> [options]`
    - Flags: `--quality` (best/worst/720/1080/…), `--audio-only`, `--audio-format`, `--output`/`-o` (template), `--output-dir`, `--rate-limit`, `--retries`, `--resume/--no-resume`, `--concurrent-fragments`
    - Map CLI flags to `DownloadOptions`; call `Orchestrator.download()`
    - Print progress to stderr; print final path to stdout on success; print error message and exit with code 1 on failure
    - Register `GenericHTTPExtractor` by default; document how to add custom extractors
    - _Requirements: CLI Entry Point, all DownloadOptions fields_

  - [~] 10.2 Expose programmatic API in `media_downloader/__init__.py`
    - Re-export `Orchestrator`, `DownloadOptions`, `DownloadResult`, `MediaManifest`, `Format`, `SelectedFormats`, `QualitySpec`
    - Add `create_orchestrator() -> Orchestrator` factory that registers default extractors
    - _Requirements: Library API_

  - [~] 10.3 Write integration tests for CLI
    - Use `click.testing.CliRunner` to invoke CLI with mocked `Orchestrator`
    - Test successful download prints final path
    - Test error exits with code 1 and message
    - Test `--audio-only` maps to `DownloadOptions.audio_only = True`
    - _Requirements: CLI Entry Point_

- [ ] 11. Property-based tests for format selection edge cases
  - [~] 11.1 Write property test for format non-empty invariant
    - **Property 1: Format Non-empty** — any successfully extracted `MediaManifest` has at least one format
    - **Validates: Requirements P1**

  - [~] 11.2 Write property test for selection always produces at least one stream
    - For any valid manifest with at least one format, `select()` in non-constrained mode returns `Ok` with at least one of `video` or `audio` set
    - **Validates: Requirements Function 2 postcondition**

- [~] 12. Final checkpoint — full test suite passes
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from §Correctness Properties
- Unit tests validate specific examples and edge cases
- `httpx` is used (not `requests`) for async-ready HTTP with native range-request support
- `hypothesis` is used for property-based tests; `pytest` for all tests
- FFmpeg must be on `PATH`; the post-processor surfaces a clear error if it is not
- Resume state is stored in a `.media_dl_resume/` directory alongside the output dir

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.3", "3.1", "5.1", "5.2", "7.1"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.2", "3.3", "3.4", "5.3", "7.2", "7.3"] },
    { "id": 3, "tasks": ["2.5", "5.4", "5.5", "5.6", "6.1"] },
    { "id": 4, "tasks": ["6.2", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "10.1"] },
    { "id": 6, "tasks": ["10.2", "10.3", "11.1", "11.2"] }
  ]
}
```
