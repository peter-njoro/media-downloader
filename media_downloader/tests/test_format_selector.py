"""
Unit tests for FormatSelector (Component 4).

Tests cover Algorithm 2 (format selection) and Algorithm 5 (quality scoring):

  - Direct FormatId selection → returns exact match or FormatIdNotFound
  - audio_only mode → picks best audio-eligible stream by audio_score
  - Combined-stream preference → picks highest-scored combined format
  - Video+audio mux path → picks best video-only + best audio-only
  - NoSuitableFormatFound when candidates are insufficient
  - quality_score: Best, Worst, Height(n) scoring
  - audio_score: ordered by audio_bitrate
  - requires_mux invariant on all returned SelectedFormats
"""

from __future__ import annotations

import pytest

from media_downloader.format_selector import FormatSelector
from media_downloader.models import (
    Best,
    DownloadOptions,
    Format,
    FormatId,
    FormatIdNotFound,
    Height,
    MediaManifest,
    NoSuitableFormatFound,
    SelectedFormats,
    StreamType,
    Worst,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_format(
    format_id: str,
    stream_type: StreamType,
    *,
    height: int | None = None,
    video_bitrate: int | None = None,
    audio_bitrate: int | None = None,
) -> Format:
    return Format(
        format_id=format_id,
        url=f"https://example.com/{format_id}",
        stream_type=stream_type,
        container="mp4",
        height=height,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
    )


def _manifest(*formats: Format) -> MediaManifest:
    return MediaManifest(id="vid1", title="Test Video", formats=list(formats))


def _opts(**kwargs) -> DownloadOptions:
    return DownloadOptions(**kwargs)


SELECTOR = FormatSelector()


# ---------------------------------------------------------------------------
# FormatId direct selection
# ---------------------------------------------------------------------------


class TestSelectByFormatId:
    def test_returns_matching_format_as_video_slot_for_combined(self) -> None:
        fmt = _make_format("best", StreamType.COMBINED, height=1080)
        manifest = _manifest(fmt)
        opts = _opts(quality=FormatId("best"))
        result = SELECTOR.select(manifest, opts)
        assert result.video is fmt
        assert result.audio is None

    def test_returns_matching_format_as_video_slot_for_video_only(self) -> None:
        fmt = _make_format("vid720", StreamType.VIDEO_ONLY, height=720)
        manifest = _manifest(fmt)
        opts = _opts(quality=FormatId("vid720"))
        result = SELECTOR.select(manifest, opts)
        assert result.video is fmt
        assert result.audio is None

    def test_returns_matching_format_as_audio_slot_for_audio_only(self) -> None:
        fmt = _make_format("aud128", StreamType.AUDIO_ONLY, audio_bitrate=128)
        manifest = _manifest(fmt)
        opts = _opts(quality=FormatId("aud128"))
        result = SELECTOR.select(manifest, opts)
        assert result.video is None
        assert result.audio is fmt

    def test_raises_format_id_not_found_when_id_missing(self) -> None:
        fmt = _make_format("existing", StreamType.COMBINED, height=720)
        manifest = _manifest(fmt)
        opts = _opts(quality=FormatId("nonexistent"))
        with pytest.raises(FormatIdNotFound) as exc_info:
            SELECTOR.select(manifest, opts)
        assert exc_info.value.format_id == "nonexistent"

    def test_format_id_selection_ignores_other_formats(self) -> None:
        """Only the exact-ID format is returned, even if others score higher."""
        low = _make_format("low", StreamType.COMBINED, height=360)
        high = _make_format("high", StreamType.COMBINED, height=1080)
        manifest = _manifest(low, high)
        opts = _opts(quality=FormatId("low"))
        result = SELECTOR.select(manifest, opts)
        assert result.video is low

    def test_requires_mux_false_for_single_format_id_selection(self) -> None:
        fmt = _make_format("c1", StreamType.COMBINED, height=720)
        manifest = _manifest(fmt)
        result = SELECTOR.select(manifest, _opts(quality=FormatId("c1")))
        assert result.requires_mux is False


# ---------------------------------------------------------------------------
# audio_only mode
# ---------------------------------------------------------------------------


class TestAudioOnlyMode:
    def test_selects_audio_only_stream(self) -> None:
        audio = _make_format("a128", StreamType.AUDIO_ONLY, audio_bitrate=128)
        video = _make_format("v720", StreamType.VIDEO_ONLY, height=720)
        manifest = _manifest(audio, video)
        opts = _opts(audio_only=True)
        result = SELECTOR.select(manifest, opts)
        assert result.video is None
        assert result.audio is audio

    def test_prefers_higher_audio_bitrate(self) -> None:
        low = _make_format("a64", StreamType.AUDIO_ONLY, audio_bitrate=64)
        high = _make_format("a320", StreamType.AUDIO_ONLY, audio_bitrate=320)
        manifest = _manifest(low, high)
        opts = _opts(audio_only=True)
        result = SELECTOR.select(manifest, opts)
        assert result.audio is high

    def test_accepts_combined_stream_for_audio_only(self) -> None:
        """Combined streams are eligible when audio_only=True."""
        combined = _make_format("combo", StreamType.COMBINED, audio_bitrate=192)
        manifest = _manifest(combined)
        opts = _opts(audio_only=True)
        result = SELECTOR.select(manifest, opts)
        assert result.audio is combined

    def test_prefers_audio_only_over_combined_when_higher_bitrate(self) -> None:
        combined = _make_format("combo", StreamType.COMBINED, audio_bitrate=128)
        audio = _make_format("aud", StreamType.AUDIO_ONLY, audio_bitrate=320)
        manifest = _manifest(combined, audio)
        opts = _opts(audio_only=True)
        result = SELECTOR.select(manifest, opts)
        assert result.audio is audio

    def test_raises_no_suitable_format_when_only_video_only_streams(self) -> None:
        video = _make_format("v1080", StreamType.VIDEO_ONLY, height=1080)
        manifest = _manifest(video)
        opts = _opts(audio_only=True)
        with pytest.raises(NoSuitableFormatFound):
            SELECTOR.select(manifest, opts)

    def test_requires_mux_false_in_audio_only_mode(self) -> None:
        audio = _make_format("a256", StreamType.AUDIO_ONLY, audio_bitrate=256)
        manifest = _manifest(audio)
        result = SELECTOR.select(manifest, _opts(audio_only=True))
        assert result.requires_mux is False


# ---------------------------------------------------------------------------
# Combined-stream preference (non-audio-only)
# ---------------------------------------------------------------------------


class TestCombinedPreference:
    def test_picks_combined_when_available(self) -> None:
        combined = _make_format("combo", StreamType.COMBINED, height=720)
        audio = _make_format("aud", StreamType.AUDIO_ONLY, audio_bitrate=128)
        manifest = _manifest(combined, audio)
        opts = _opts()
        result = SELECTOR.select(manifest, opts)
        assert result.video is combined
        assert result.audio is None

    def test_picks_best_combined_by_quality_score_best(self) -> None:
        low = _make_format("c360", StreamType.COMBINED, height=360)
        high = _make_format("c1080", StreamType.COMBINED, height=1080)
        manifest = _manifest(low, high)
        opts = _opts(quality=Best())
        result = SELECTOR.select(manifest, opts)
        assert result.video is high

    def test_picks_worst_combined_by_quality_score_worst(self) -> None:
        low = _make_format("c360", StreamType.COMBINED, height=360)
        high = _make_format("c1080", StreamType.COMBINED, height=1080)
        manifest = _manifest(low, high)
        opts = _opts(quality=Worst())
        result = SELECTOR.select(manifest, opts)
        assert result.video is low

    def test_picks_closest_height_combined(self) -> None:
        c360 = _make_format("c360", StreamType.COMBINED, height=360)
        c720 = _make_format("c720", StreamType.COMBINED, height=720)
        c1080 = _make_format("c1080", StreamType.COMBINED, height=1080)
        manifest = _manifest(c360, c720, c1080)
        opts = _opts(quality=Height(800))
        result = SELECTOR.select(manifest, opts)
        # 800 is closest to 720 (diff=80) vs 1080 (diff=280)
        assert result.video is c720

    def test_requires_mux_false_for_combined(self) -> None:
        combined = _make_format("combo", StreamType.COMBINED, height=1080)
        manifest = _manifest(combined)
        result = SELECTOR.select(manifest, _opts())
        assert result.requires_mux is False


# ---------------------------------------------------------------------------
# Video+audio mux path
# ---------------------------------------------------------------------------


class TestMuxPath:
    def test_mux_path_when_no_combined_available(self) -> None:
        video = _make_format("v1080", StreamType.VIDEO_ONLY, height=1080)
        audio = _make_format("a128", StreamType.AUDIO_ONLY, audio_bitrate=128)
        manifest = _manifest(video, audio)
        opts = _opts()
        result = SELECTOR.select(manifest, opts)
        assert result.video is video
        assert result.audio is audio
        assert result.requires_mux is True

    def test_mux_picks_best_video_and_best_audio(self) -> None:
        v720 = _make_format("v720", StreamType.VIDEO_ONLY, height=720)
        v1080 = _make_format("v1080", StreamType.VIDEO_ONLY, height=1080)
        a64 = _make_format("a64", StreamType.AUDIO_ONLY, audio_bitrate=64)
        a256 = _make_format("a256", StreamType.AUDIO_ONLY, audio_bitrate=256)
        manifest = _manifest(v720, v1080, a64, a256)
        opts = _opts(quality=Best())
        result = SELECTOR.select(manifest, opts)
        assert result.video is v1080
        assert result.audio is a256

    def test_mux_worst_picks_lowest_video(self) -> None:
        v480 = _make_format("v480", StreamType.VIDEO_ONLY, height=480)
        v1080 = _make_format("v1080", StreamType.VIDEO_ONLY, height=1080)
        audio = _make_format("aud", StreamType.AUDIO_ONLY, audio_bitrate=128)
        manifest = _manifest(v480, v1080, audio)
        opts = _opts(quality=Worst())
        result = SELECTOR.select(manifest, opts)
        assert result.video is v480

    def test_mux_requires_mux_true(self) -> None:
        video = _make_format("vid", StreamType.VIDEO_ONLY, height=720)
        audio = _make_format("aud", StreamType.AUDIO_ONLY, audio_bitrate=128)
        manifest = _manifest(video, audio)
        result = SELECTOR.select(manifest, _opts())
        assert result.requires_mux is True


# ---------------------------------------------------------------------------
# Single direct-download fallback
# ---------------------------------------------------------------------------


class TestSingleDirectFormatSelection:
    def test_selects_single_direct_format_when_present(self) -> None:
        fmt = Format(
            format_id="direct",
            url="https://example.com/image.jpg",
            stream_type=StreamType.VIDEO_ONLY,
            container="jpeg",
        )
        manifest = _manifest(fmt)
        result = SELECTOR.select(manifest, _opts())
        assert result.video is fmt
        assert result.audio is None


# ---------------------------------------------------------------------------
# NoSuitableFormatFound
# ---------------------------------------------------------------------------


class TestNoSuitableFormat:
    def test_raises_when_only_video_only_streams(self) -> None:
        video = _make_format("v720", StreamType.VIDEO_ONLY, height=720)
        manifest = _manifest(video)
        with pytest.raises(NoSuitableFormatFound):
            SELECTOR.select(manifest, _opts())

    def test_raises_when_only_audio_only_streams_in_non_audio_mode(self) -> None:
        audio = _make_format("a128", StreamType.AUDIO_ONLY, audio_bitrate=128)
        manifest = _manifest(audio)
        with pytest.raises(NoSuitableFormatFound):
            SELECTOR.select(manifest, _opts(audio_only=False))


# ---------------------------------------------------------------------------
# quality_score (Algorithm 5)
# ---------------------------------------------------------------------------


class TestQualityScore:
    def test_best_score_uses_height_video_audio_bitrate(self) -> None:
        fmt = _make_format("f", StreamType.COMBINED, height=720, video_bitrate=2000, audio_bitrate=128)
        opts = _opts(quality=Best())
        score = SELECTOR._quality_score(fmt, opts)
        assert score == 720 * 10_000 + 2000 + 128

    def test_worst_score_is_negated_best(self) -> None:
        fmt = _make_format("f", StreamType.COMBINED, height=1080, video_bitrate=5000, audio_bitrate=256)
        best_score = SELECTOR._quality_score(fmt, _opts(quality=Best()))
        worst_score = SELECTOR._quality_score(fmt, _opts(quality=Worst()))
        assert worst_score == -best_score

    def test_height_score_is_negative_absolute_difference(self) -> None:
        fmt = _make_format("f", StreamType.COMBINED, height=720)
        score = SELECTOR._quality_score(fmt, _opts(quality=Height(1080)))
        assert score == -abs(720 - 1080)

    def test_height_exact_match_scores_zero(self) -> None:
        fmt = _make_format("f", StreamType.COMBINED, height=1080)
        score = SELECTOR._quality_score(fmt, _opts(quality=Height(1080)))
        assert score == 0.0

    def test_missing_height_treated_as_zero(self) -> None:
        fmt = _make_format("f", StreamType.AUDIO_ONLY, audio_bitrate=128)
        # height is None → treated as 0
        score = SELECTOR._quality_score(fmt, _opts(quality=Best()))
        assert score == 128

    def test_missing_bitrates_treated_as_zero(self) -> None:
        fmt = _make_format("f", StreamType.VIDEO_ONLY, height=720)
        score = SELECTOR._quality_score(fmt, _opts(quality=Best()))
        assert score == 720 * 10_000

    def test_best_scores_higher_for_higher_resolution(self) -> None:
        low = _make_format("low", StreamType.COMBINED, height=360)
        high = _make_format("high", StreamType.COMBINED, height=1080)
        opts = _opts(quality=Best())
        assert SELECTOR._quality_score(high, opts) > SELECTOR._quality_score(low, opts)

    def test_worst_scores_higher_for_lower_resolution(self) -> None:
        low = _make_format("low", StreamType.COMBINED, height=240)
        high = _make_format("high", StreamType.COMBINED, height=1080)
        opts = _opts(quality=Worst())
        assert SELECTOR._quality_score(low, opts) > SELECTOR._quality_score(high, opts)


# ---------------------------------------------------------------------------
# audio_score
# ---------------------------------------------------------------------------


class TestAudioScore:
    def test_returns_audio_bitrate(self) -> None:
        fmt = _make_format("a", StreamType.AUDIO_ONLY, audio_bitrate=256)
        assert SELECTOR._audio_score(fmt) == 256.0

    def test_missing_audio_bitrate_returns_zero(self) -> None:
        fmt = _make_format("a", StreamType.AUDIO_ONLY)
        assert SELECTOR._audio_score(fmt) == 0.0

    def test_higher_bitrate_scores_higher(self) -> None:
        low = _make_format("l", StreamType.AUDIO_ONLY, audio_bitrate=64)
        high = _make_format("h", StreamType.AUDIO_ONLY, audio_bitrate=320)
        assert SELECTOR._audio_score(high) > SELECTOR._audio_score(low)


# ---------------------------------------------------------------------------
# requires_mux invariant (P2 / correctness property)
# ---------------------------------------------------------------------------


class TestRequiresMuxInvariant:
    """P2: requires_mux iff both video and audio are non-None."""

    def _check_invariant(self, result: SelectedFormats) -> None:
        expected = result.video is not None and result.audio is not None
        assert result.requires_mux == expected

    def test_invariant_combined_stream(self) -> None:
        fmt = _make_format("c", StreamType.COMBINED, height=720)
        result = SELECTOR.select(_manifest(fmt), _opts())
        self._check_invariant(result)

    def test_invariant_mux_path(self) -> None:
        video = _make_format("v", StreamType.VIDEO_ONLY, height=720)
        audio = _make_format("a", StreamType.AUDIO_ONLY, audio_bitrate=128)
        result = SELECTOR.select(_manifest(video, audio), _opts())
        self._check_invariant(result)

    def test_invariant_audio_only_mode(self) -> None:
        audio = _make_format("a", StreamType.AUDIO_ONLY, audio_bitrate=128)
        result = SELECTOR.select(_manifest(audio), _opts(audio_only=True))
        self._check_invariant(result)

    def test_invariant_format_id_combined(self) -> None:
        fmt = _make_format("c", StreamType.COMBINED, height=720)
        result = SELECTOR.select(_manifest(fmt), _opts(quality=FormatId("c")))
        self._check_invariant(result)

    def test_invariant_format_id_audio(self) -> None:
        fmt = _make_format("a", StreamType.AUDIO_ONLY, audio_bitrate=128)
        result = SELECTOR.select(_manifest(fmt), _opts(quality=FormatId("a")))
        self._check_invariant(result)
