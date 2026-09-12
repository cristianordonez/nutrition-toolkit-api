"""Agent tools for searching the clinical knowledge vector indexes."""

from __future__ import annotations

import typing
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import FunctionToolset, RunContext

from ntk.models.knowledge import KnowledgeType

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from ntk.models.rag import RagSearchMatch
    from ntk.services.embedding_service import EmbeddingService

_KNOWLEDGE_MATCH_LIMIT = 3


@dataclass(frozen=True)
class KnowledgeSearchToolDependencies:
    """Runtime service required by the knowledge-search tools."""

    embedding_service: EmbeddingService


class RagSearchInput(BaseModel):
    """One focused clinical question for semantic manual search."""

    query: str = Field(
        description=(
            "Focused nutrition or diet question to search for in the selected "
            "clinical manual"
        ),
        min_length=1,
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        """Remove surrounding whitespace and reject empty search text."""
        normalized = value.strip()
        if not normalized:
            msg = "Search query must not be empty"
            raise ValueError(msg)
        return normalized


async def get_knowledge_from_nutrition_care_manual(
    ctx: RunContext[KnowledgeSearchToolDependencies],
    data: RagSearchInput,
) -> dict[str, object]:
    """Retrieve clinical nutrition guidance from the Nutrition Care Manual.

    Use for clinical nutrition assessment and intervention questions, including
    disease-specific nutrition care, nutrient requirements, malnutrition, and
    enteral or parenteral nutrition. Do not use it merely to identify a facility
    diet definition when the Diet Manual is the more specific source.
    """
    matches = await ctx.deps.embedding_service.search_knowledge(
        data.query,
        _KNOWLEDGE_MATCH_LIMIT,
        document_type=KnowledgeType.NUTRITION_CARE_MANUAL,
    )
    return _search_payload("nutrition-care-manual", data.query, matches)


async def get_knowledge_from_diet_manual(
    ctx: RunContext[KnowledgeSearchToolDependencies],
    data: RagSearchInput,
) -> dict[str, object]:
    """Retrieve diet-order and food-service guidance from the Diet Manual.

    Use for questions about named therapeutic diets, restrictions, textures,
    liquid consistencies, permitted foods, and facility diet implementation.
    Use the Nutrition Care Manual instead for broader clinical assessment or
    disease-specific nutrition-care guidance.
    """
    matches = await ctx.deps.embedding_service.search_knowledge(
        data.query,
        _KNOWLEDGE_MATCH_LIMIT,
        document_type=KnowledgeType.DIET_MANUAL,
    )
    return _search_payload("diet-manual", data.query, matches)


def _search_payload(
    source: str,
    query: str,
    matches: Sequence[RagSearchMatch],
) -> dict[str, object]:
    """Return a consistent JSON-compatible tool result."""
    return {
        "source": source,
        "query": query,
        "matches": [match.model_dump(mode="json") for match in matches],
    }


KNOWLEDGE_SEARCH_TOOLSET = FunctionToolset[KnowledgeSearchToolDependencies](
    id="knowledge",
)
KNOWLEDGE_SEARCH_TOOLSET.add_function(
    get_knowledge_from_nutrition_care_manual,
    name="get_knowledge_from_nutrition_care_manual",
    description=(
        "Search the Nutrition Care Manual for clinical nutrition assessment and "
        "intervention guidance, such as disease-specific care, nutrient needs, "
        "malnutrition, and enteral or parenteral nutrition. Use only when the "
        "provided person facts do not already answer the clinical guidance question."
    ),
)
KNOWLEDGE_SEARCH_TOOLSET.add_function(
    get_knowledge_from_diet_manual,
    name="get_knowledge_from_diet_manual",
    description=(
        "Search the Diet Manual for diet-order definitions and implementation "
        "guidance, including therapeutic diets, restrictions, textures, liquid "
        "consistencies, and permitted foods. Do not use it for person facts or "
        "general disease-specific nutrition-care guidance."
    ),
)


__all__ = [
    "KNOWLEDGE_SEARCH_TOOLSET",
    "KnowledgeSearchToolDependencies",
    "RagSearchInput",
    "get_knowledge_from_diet_manual",
    "get_knowledge_from_nutrition_care_manual",
]
