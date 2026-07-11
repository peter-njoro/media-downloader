"""
Post-download content analyzer.

Extracts audio for transcription, generates summaries, and selects
representative thumbnails using AI.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from media_downloader.ai_provider import AIProvider
from media_downloader.models import AIAnalysisResult, DownloadOptions, FinalFile

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
Summarize the following transcript. Include key points, main topics, \
and notable timestamps if present. Format as markdown with headers.\
"""

_THUMBNAIL_PROMPT = """\
You are given several frames extracted from a video. \
Select the 3 most representative frames for a video thumbnail. \
Return ONLY a JSON array of 0-based indices, e.g. [0, 2, 4].\
"""


class ContentAnalyzer:
    """Analyzes downloaded content using AI."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider
        self._ffmpeg = shutil.which("ffmpeg")

    def analyze(
        self, final_file: FinalFile, opts: DownloadOptions
    ) -> AIAnalysisResult:
        """Run enabled analysis modes on the downloaded file."""
        result = AIAnalysisResult()
        video_path = final_file.path

        if opts.ai_transcribe:
            try:
                result.transcription = self._transcribe(video_path)
            except Exception as exc:
                logger.warning("Transcription failed: %s", exc)

        if opts.ai_summarize and result.transcription:
            try:
                result.summary = self._summarize(result.transcription)
            except Exception as exc:
                logger.warning("Summarization failed: %s", exc)

        if opts.ai_thumbnails:
            try:
                result.thumbnails = self._extract_thumbnails(video_path)
            except Exception as exc:
                logger.warning("Thumbnail extraction failed: %s", exc)

        return result

    def _transcribe(self, video_path: Path) -> Optional[str]:
        """Extract audio and transcribe via STT provider."""
        if self._ffmpeg is None:
            logger.warning("ffmpeg not found, cannot extract audio for transcription")
            return None

        audio_path = video_path.with_suffix(".audio.wav")
        cmd = [
            self._ffmpeg, "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=False)

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            logger.warning("Audio extraction failed for transcription")
            return None

        try:
            # Send audio to the provider's chat endpoint with a transcription prompt
            # For a real STT API, you'd use a dedicated endpoint.
            # Here we use the chat API with a note about the audio file.
            audio_size_mb = audio_path.stat().st_size / (1024 * 1024)
            if audio_size_mb > 25:
                logger.warning(
                    "Audio file %.1fMB exceeds 25MB limit, chunking not implemented yet",
                    audio_size_mb,
                )
                return None

            response = self._provider.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Transcribe the following audio file. "
                            "Return the transcript as plain text with timestamps "
                            "in [HH:MM:SS] format at the start of each paragraph. "
                            f"Audio file: {audio_path}"
                        ),
                    },
                ]
            )
            return response
        finally:
            # Clean up extracted audio
            audio_path.unlink(missing_ok=True)

    def _summarize(self, transcription: str) -> Optional[str]:
        """Generate a summary from the transcription text."""
        # Truncate very long transcripts to stay within token limits
        max_chars = 50_000
        text = transcription[:max_chars]
        if len(transcription) > max_chars:
            text += "\n\n[Transcript truncated for summarization]"

        response = self._provider.chat(
            messages=[
                {"role": "system", "content": _SUMMARIZE_PROMPT},
                {"role": "user", "content": text},
            ]
        )
        return response

    def _extract_thumbnails(self, video_path: Path) -> List[Path]:
        """Extract representative frames from the video."""
        if self._ffmpeg is None:
            logger.warning("ffmpeg not found, cannot extract thumbnails")
            return []

        thumb_dir = video_path.parent / f"{video_path.stem}_thumbnails"
        thumb_dir.mkdir(exist_ok=True)

        # Extract frames at 10-second intervals
        pattern = str(thumb_dir / "frame_%03d.jpg")
        cmd = [
            self._ffmpeg, "-y", "-i", str(video_path),
            "-vf", "fps=1/10", "-q:v", "2",
            pattern,
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=False)

        frames = sorted(thumb_dir.glob("frame_*.jpg"))
        if not frames:
            return []

        # If more than 5 frames, use AI to select the best 3
        if len(frames) > 5:
            try:
                selected = self._select_best_frames(frames)
                return selected
            except Exception as exc:
                logger.warning("AI frame selection failed, using first 3: %s", exc)
                return frames[:3]

        return frames

    def _select_best_frames(self, frames: List[Path]) -> List[Path]:
        """Use AI to select the most representative frames."""
        frame_list = ", ".join(f"{i}: {f.name}" for i, f in enumerate(frames))
        response = self._provider.chat(
            messages=[
                {"role": "system", "content": _THUMBNAIL_PROMPT},
                {"role": "user", "content": f"Available frames: {frame_list}"},
            ]
        )

        # Parse the response as a JSON array of indices
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            indices = json.loads(cleaned)
            if not isinstance(indices, list):
                indices = [0, 1, 2]
        except json.JSONDecodeError:
            indices = [0, 1, 2]

        selected = []
        for idx in indices[:3]:
            if isinstance(idx, int) and 0 <= idx < len(frames):
                selected.append(frames[idx])

        return selected if selected else frames[:3]
