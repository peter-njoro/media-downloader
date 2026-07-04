"""
Abstract base class for all media extractors.

Each extractor is responsible for a specific platform or URL pattern.
Concrete implementations must declare which URLs they handle and how
to extract a :class:`~media_downloader.models.MediaManifest` from them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from media_downloader.models import ExtractionError, MediaManifest


class Extractor(ABC):
    """Abstract base class for platform-specific media extractors.

    An extractor performs two roles:

    1. **URL matching** — :meth:`can_handle` determines whether this
       extractor is capable of processing a given URL.  The
       :class:`~media_downloader.registry.ExtractorRegistry` iterates
       over registered extractors in order and returns the first one
       whose :meth:`can_handle` returns ``True``.

    2. **Manifest extraction** — :meth:`extract` fetches the page or
       platform API for the URL and returns a fully-populated
       :class:`~media_downloader.models.MediaManifest` containing all
       available streams and metadata.

    Subclasses **must** implement both abstract methods.  They may also
    expose additional configuration (e.g. API keys, cookies) via their
    ``__init__`` method.

    Example::

        class MyExtractor(Extractor):
            def can_handle(self, url: str) -> bool:
                return "myplatform.com" in url

            def extract(self, url: str) -> MediaManifest:
                # Fetch page and build manifest ...
                return MediaManifest(id="...", title="...", formats=[...])
    """

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return ``True`` if this extractor can process *url*.

        This method must be **pure** and **side-effect free** — it should
        only inspect the URL string, never issue network requests or read
        from disk.  It must also be deterministic: repeated calls with
        the same URL must return the same value.

        Args:
            url: The URL to test.  May be any non-empty string; the
                extractor is responsible for its own URL validation.

        Returns:
            ``True`` if this extractor can attempt to extract a manifest
            from *url*; ``False`` otherwise.
        """

    @abstractmethod
    def extract(self, url: str) -> MediaManifest:
        """Extract a :class:`~media_downloader.models.MediaManifest` from *url*.

        Implementations should fetch the page or platform API associated
        with *url*, parse all available stream information, and return a
        fully-populated :class:`~media_downloader.models.MediaManifest`.

        This method may perform network I/O.  Callers should not assume
        it is fast or side-effect free.

        Args:
            url: The URL to extract media information from.  Callers
                will only pass URLs for which :meth:`can_handle` returned
                ``True``, but implementations should handle unexpected
                inputs gracefully.

        Returns:
            A :class:`~media_downloader.models.MediaManifest` with at
            least one :class:`~media_downloader.models.Format` and a
            non-empty ``id`` field.

        Raises:
            ExtractionError: If extraction fails for any reason, including
                network errors, parsing failures, geo-blocking, or
                authentication requirements.  Subclasses may raise more
                specific subclasses of :class:`~media_downloader.models.ExtractionError`
                (e.g. :class:`~media_downloader.models.NetworkError`).
        """
