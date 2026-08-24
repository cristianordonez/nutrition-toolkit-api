from __future__ import annotations

import functools
import typing

from pypdf import PdfReader

from ntk.models.knowledge import KnowledgeType
from ntk.utils.tokens import sliding_window

from .base import BaseExtractor
from .registry import register_extractor


class KnowledgeExtractor(BaseExtractor):
    """Shared behavior for knowledge document extractors."""

    knowledge_type: typing.ClassVar[KnowledgeType]

    @functools.cached_property
    def reader(self) -> PdfReader:
        """Return a cached PDF reader for the knowledge document."""
        return PdfReader(self.path)

    def create_chunks(self) -> list[str]:
        """Create searchable chunks from the document."""
        entire_text = "\n".join(page.extract_text() for page in self.reader.pages)
        return sliding_window(entire_text)

    def extract(self) -> list[str]:
        """Extract searchable text chunks from the knowledge document."""
        return self.create_chunks()


@register_extractor
class NutritionCareManualExtractor(KnowledgeExtractor):
    """Recognize and chunk a clinical knowledge document."""

    knowledge_type = KnowledgeType.NUTRITION_CARE_MANUAL

    def is_expected_format(self) -> bool:
        """Return whether the document is a supported knowledge source."""
        return self._first_page_contains("Nutrition Care Manual")


@register_extractor
class DietManualExtractor(KnowledgeExtractor):
    """Recognize and chunk a clinical knowledge document."""

    knowledge_type = KnowledgeType.DIET_MANUAL

    def is_expected_format(self) -> bool:
        """Return whether the document is a supported knowledge source."""
        return self._first_page_contains("Diet Manual")
