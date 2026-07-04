"""
ExtractorRegistry — maintains an ordered list of platform extractors and
resolves which one handles a given URL.

The registry iterates extractors in registration order and returns the first
one whose ``can_handle`` predicate returns True for the URL (Algorithm 4 in
the design document).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from media_downloader.extractors.base import Extractor


class ExtractorRegistry:
    """Ordered registry of :class:`~media_downloader.extractors.base.Extractor` instances.

    Extractors are matched against URLs in the order they were registered;
    the first extractor whose ``can_handle`` method returns ``True`` is
    returned by :meth:`resolve`.
    """

    def __init__(self) -> None:
        self._extractors: List[Extractor] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, extractor: "Extractor") -> None:
        """Append *extractor* to the end of the ordered list.

        Args:
            extractor: An :class:`~media_downloader.extractors.base.Extractor`
                instance to add to the registry.
        """
        self._extractors.append(extractor)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def resolve(self, url: str) -> "Optional[Extractor]":
        """Return the first registered extractor that can handle *url*.

        Iterates extractors in registration order and returns the first one
        whose :meth:`~media_downloader.extractors.base.Extractor.can_handle`
        method returns ``True``.  Returns ``None`` if no extractor matches.

        Args:
            url: The URL to resolve an extractor for.

        Returns:
            The first matching extractor, or ``None`` if none match.
        """
        for extractor in self._extractors:
            if extractor.can_handle(url):
                return extractor
        return None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def extractors(self) -> "List[Extractor]":
        """A copy of the current ordered list of registered extractors."""
        return list(self._extractors)
