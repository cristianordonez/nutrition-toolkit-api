from __future__ import annotations

from ntk.models.knowledge import KnowledgeType

from .base import KnowledgeExtractor
from .registry import register_extractor


@register_extractor
class NutritionCareManualExtractor(KnowledgeExtractor):
    """Recognize and chunk a clinical knowledge document."""

    knowledge_type = KnowledgeType.NUTRITION_CARE_MANUAL

    def is_expected_format(self) -> bool:
        """Return whether the document is a supported knowledge source."""
        return self._is_pdf(self.path) and self._first_page_contains(
            "Nutrition Care Manual",
        )


@register_extractor
class DietManualExtractor(KnowledgeExtractor):
    """Recognize and chunk a clinical knowledge document."""

    knowledge_type = KnowledgeType.DIET_MANUAL

    def is_expected_format(self) -> bool:
        """Return whether the document is a supported knowledge source."""
        return self._is_pdf(self.path) and self._first_page_contains("Diet Manual")
