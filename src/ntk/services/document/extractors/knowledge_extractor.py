from __future__ import annotations

import typing
from hashlib import sha256

from ntk.models.knowledge import KnowledgeType
from ntk.models.sql.knowledge import Knowledge
from ntk.utils.tokens import sliding_window

from .base import BaseExtractor
from .registry import register_extractor


class KnowledgeExtractor(BaseExtractor):
    """Shared behavior for knowledge document extractors."""

    knowledge_type: typing.ClassVar[KnowledgeType]

    def extract(self) -> list[str]:
        """Extract searchable text chunks from the knowledge document."""
        return sliding_window(self._document_text)

    def create_knowledge(self) -> Knowledge:
        """Create the persisted identity for this knowledge source."""
        return Knowledge(
            filename=self.path.name,
            knowledge_type=self.knowledge_type,
            file_hash=sha256(self.path.read_bytes()).hexdigest(),
        )


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
