"""
Format Selector — Component 4.

Given a :class:`~media_downloader.models.MediaManifest` and user
:class:`~media_downloader.models.DownloadOptions`, returns the optimal set of
streams to download as a :class:`~media_downloader.models.SelectedFormats`.

Selection logic follows Algorithm 2 and quality scoring follows Algorithm 5
from the design document.
"""

from __future__ import annotations

from typing import List

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
    SelectionError,
    StreamType,
    Worst,
)


class FormatSelector:
    """Selects the best format(s) from a :class:`MediaManifest`.

    Usage::

        selector = FormatSelector()
        selected = selector.select(manifest, opts)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(
        self,
        manifest: MediaManifest,
        opts: DownloadOptions,
    ) -> SelectedFormats:
        """Return the optimal :class:`SelectedFormats` for *manifest* and *opts*.

        Parameters
        ----------
        manifest:
            The fully-populated media manifest produced by an extractor.
        opts:
            User-supplied download options including quality spec and
            ``audio_only`` flag.

        Returns
        -------
        SelectedFormats
            Contains ``video`` and/or ``audio`` :class:`Format` objects, plus
            the derived ``requires_mux`` flag.

        Raises
        ------
        FormatIdNotFound
            When ``opts.quality`` is a :class:`FormatId` whose value is not
            present in ``manifest.formats``.
        NoSuitableFormatFound
            When no format in the manifest satisfies the given constraints.
        SelectionError
            For any other selection-level failure.
        """
        # Branch 1 — direct format-id selection (Algorithm 2, first block)
        if isinstance(opts.quality, FormatId):
            return self._select_by_id(manifest.formats, opts.quality.value)

        candidates: List[Format] = list(manifest.formats)

        # Branch 2 — audio-only mode (Algorithm 2, second block)
        if opts.audio_only:
            return self._select_audio_only(candidates)

        # Branch 3 — prefer combined; fall back to video+audio mux
        return self._select_video(candidates, opts)

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _quality_score(self, fmt: Format, opts: DownloadOptions) -> float:
        """Compute a quality score for *fmt* given *opts*.

        Scoring rules (Algorithm 5):

        * ``Best``      →  ``height * 10_000 + video_bitrate + audio_bitrate``
        * ``Worst``     →  negated Best score
        * ``Height(n)`` →  ``-abs(height - n)``

        Missing numeric fields are treated as 0.

        Parameters
        ----------
        fmt:
            The format to score.
        opts:
            Download options containing the active :class:`QualitySpec`.

        Returns
        -------
        float
            Higher values are preferred (``argmax`` semantics).
        """
        h: int = fmt.height if fmt.height is not None else 0
        vb: int = fmt.video_bitrate if fmt.video_bitrate is not None else 0
        ab: int = fmt.audio_bitrate if fmt.audio_bitrate is not None else 0

        if isinstance(opts.quality, Best):
            return float(h * 10_000 + vb + ab)

        if isinstance(opts.quality, Worst):
            return float(-(h * 10_000 + vb + ab))

        if isinstance(opts.quality, Height):
            return float(-abs(h - opts.quality.value))

        # FormatId is handled before this method is ever called; this branch
        # is a safety net for unexpected subclasses.
        return float(h * 10_000 + vb + ab)

    def _audio_score(self, fmt: Format) -> float:
        """Return a score for audio-only selection based on audio bitrate.

        Parameters
        ----------
        fmt:
            The format to score.

        Returns
        -------
        float
            Higher values are preferred (``argmax`` semantics).
        """
        return float(fmt.audio_bitrate if fmt.audio_bitrate is not None else 0)

    # ------------------------------------------------------------------
    # Private selection helpers
    # ------------------------------------------------------------------

    def _select_by_id(
        self,
        formats: List[Format],
        format_id: str,
    ) -> SelectedFormats:
        """Select a single format by its ``format_id``.

        Parameters
        ----------
        formats:
            All formats from the manifest.
        format_id:
            The exact format identifier to look up.

        Raises
        ------
        FormatIdNotFound
            When no format with ``format_id`` exists in *formats*.
        """
        for fmt in formats:
            if fmt.format_id == format_id:
                # Wrap the single format appropriately based on stream type.
                if fmt.stream_type == StreamType.AUDIO_ONLY:
                    return SelectedFormats(video=None, audio=fmt)
                # VideoOnly or Combined — treat as the video slot so the
                # mux invariant is satisfied (no separate audio needed).
                return SelectedFormats(video=fmt, audio=None)

        raise FormatIdNotFound(format_id)

    def _select_audio_only(self, candidates: List[Format]) -> SelectedFormats:
        """Select the best audio stream for audio-only mode.

        Eligible stream types are ``AudioOnly`` and ``Combined`` (Algorithm 2).

        Parameters
        ----------
        candidates:
            All formats from the manifest.

        Raises
        ------
        NoSuitableFormatFound
            When no audio-eligible format is found.
        """
        audio_candidates = [
            f
            for f in candidates
            if f.stream_type in (StreamType.AUDIO_ONLY, StreamType.COMBINED)
        ]

        if not audio_candidates:
            available_heights = [f.height for f in candidates]
            raise NoSuitableFormatFound(available_heights)

        best = max(audio_candidates, key=self._audio_score)
        return SelectedFormats(video=None, audio=best)

    def _select_video(
        self,
        candidates: List[Format],
        opts: DownloadOptions,
    ) -> SelectedFormats:
        """Select the best video stream, preferring combined over mux.

        Algorithm 2 logic:

        1. If any ``Combined`` streams exist, pick the best-scored one.
        2. Else if both ``VideoOnly`` and ``AudioOnly`` streams exist, pair
           the best of each (``requires_mux = True``).
        3. Otherwise raise :class:`NoSuitableFormatFound`.

        Parameters
        ----------
        candidates:
            All formats from the manifest.
        opts:
            Download options used for scoring.

        Raises
        ------
        NoSuitableFormatFound
            When neither a combined stream nor a VideoOnly+AudioOnly pair is
            available.
        """
        combined = [f for f in candidates if f.stream_type == StreamType.COMBINED]
        video_only = [f for f in candidates if f.stream_type == StreamType.VIDEO_ONLY]
        audio_only = [f for f in candidates if f.stream_type == StreamType.AUDIO_ONLY]

        if combined:
            best = max(combined, key=lambda f: self._quality_score(f, opts))
            return SelectedFormats(video=best, audio=None)

        if video_only and audio_only:
            best_video = max(video_only, key=lambda f: self._quality_score(f, opts))
            best_audio = max(audio_only, key=self._audio_score)
            return SelectedFormats(video=best_video, audio=best_audio)

        available_heights = [f.height for f in candidates]
        raise NoSuitableFormatFound(available_heights)
