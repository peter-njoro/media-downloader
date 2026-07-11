"""
Content-aware quality advisor.

Classifies media content type via LLM and recommends the optimal format.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from media_downloader.ai_provider import AIProvider
from media_downloader.models import AIQualityAdvice, MediaManifest

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a media content classifier. Given metadata about a media item, \
classify its content type and recommend the optimal download format.

Content types:
- "lecture": Educational content, long-form (>20 min), talks, tutorials
- "music_video": Music performance, 2-8 min, music-related
- "podcast": Audio-focused content, long-form (>15 min)
- "short_clip": Short-form content (<60 sec), social media clips
- "archival": No strong signal, or explicitly archival quality

Return ONLY a JSON object:
{
  "content_type": "lecture",
  "recommended_format_id": "format-id-or-null",
  "reasoning": "Brief explanation of why this format was recommended"
}

Rules:
- recommended_format_id must be one of the format IDs listed in the available formats, or null for best quality
- If unsure, classify as "archival" and recommend null
"""

_VALID_TYPES = {"lecture", "music_video", "podcast", "short_clip", "archival"}


class QualityAdvisor:
    """Recommends optimal format based on content type classification."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def advise(self, manifest: MediaManifest) -> AIQualityAdvice:
        """Classify content and recommend a format."""
        metadata = self._build_metadata(manifest)
        format_ids = [f.format_id for f in manifest.formats]

        prompt = (
            f"Available format IDs: {format_ids}\n"
            f"Content metadata:\n{metadata}"
        )

        try:
            response = self._provider.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            parsed = self._parse_response(response)
        except Exception as exc:
            logger.warning("Quality advisor failed: %s", exc)
            return AIQualityAdvice(
                content_type="unknown",
                recommended_format_id=None,
                reasoning=f"AI unavailable: {exc}",
            )

        content_type = parsed.get("content_type", "unknown")
        if content_type not in _VALID_TYPES:
            content_type = "unknown"

        rec_id = parsed.get("recommended_format_id")
        if rec_id is not None and rec_id not in format_ids:
            rec_id = None

        return AIQualityAdvice(
            content_type=content_type,
            recommended_format_id=rec_id,
            reasoning=parsed.get("reasoning", ""),
        )

    def _build_metadata(self, manifest: MediaManifest) -> str:
        """Build a text summary of the manifest for the LLM."""
        lines: List[str] = []
        if manifest.title:
            lines.append(f"Title: {manifest.title}")
        if manifest.description:
            lines.append(f"Description: {manifest.description[:200]}")
        if manifest.duration is not None:
            lines.append(f"Duration: {manifest.duration}s")
        if manifest.uploader:
            lines.append(f"Uploader: {manifest.uploader}")

        lines.append(f"Available formats ({len(manifest.formats)}):")
        for fmt in manifest.formats:
            parts = [f"  id={fmt.format_id}", f"type={fmt.stream_type.value}"]
            if fmt.height is not None:
                parts.append(f"height={fmt.height}p")
            if fmt.video_bitrate is not None:
                parts.append(f"vbr={fmt.video_bitrate}kbps")
            if fmt.audio_bitrate is not None:
                parts.append(f"abr={fmt.audio_bitrate}kbps")
            parts.append(f"container={fmt.container}")
            lines.append(" ".join(parts))

        return "\n".join(lines)

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from the LLM response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON object
            import re
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        logger.warning("Failed to parse quality advisor response")
        return {"content_type": "unknown", "recommended_format_id": None, "reasoning": "unparseable response"}
