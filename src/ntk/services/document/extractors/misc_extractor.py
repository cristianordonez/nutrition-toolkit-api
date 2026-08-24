from __future__ import annotations

from .base import BaseExtractor
from .registry import register_extractor


@register_extractor
class MiscExtractor(BaseExtractor):
    """Recognize a document that has no specialized extractor."""

    def is_expected_format(self) -> bool:
        """Return whether the document should use miscellaneous extraction."""
        return True
