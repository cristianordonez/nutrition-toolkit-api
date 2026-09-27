"""Manual lookups the note-generation agent can call.

Ported from the server, which searched a pgvector knowledge base. The manuals
now ship inside the application's own database, so these run on-device with no
network and no account.

The tools answer *general* clinical questions -- what a therapeutic diet
permits, what the nutrition-care guidance for a condition is. They are never a
source of fact about the resident: everything true of this person arrives in
the prompt already, and the prompt says so.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import FunctionToolset, RunContext

from engine.models.sql.knowledge import KnowledgeType

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from engine.models.rag import RagSearchMatch
    from engine.services.knowledge_service import KnowledgeService

#: Enough passages to answer a focused question without crowding the context
#: budget the note itself needs.
_KNOWLEDGE_MATCH_LIMIT = 5


@dataclass(frozen=True)
class KnowledgeSearchToolDependencies:
    """Runtime service the manual-search tools need.

    Optional, because a note is still worth writing without it. A device whose
    reference content has not been installed yet, or a caller that did not
    wire one up, makes the lookups unavailable rather than making generation
    impossible -- the prompt's own clinical rules and the resident's supplied
    facts do not depend on the manuals.
    """

    knowledge_service: KnowledgeService | None = None


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
    return await _search(
        ctx,
        "nutrition-care-manual",
        data.query,
        KnowledgeType.NUTRITION_CARE_MANUAL,
    )


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
    return await _search(ctx, "diet-manual", data.query, KnowledgeType.DIET_MANUAL)


async def _search(
    ctx: RunContext[KnowledgeSearchToolDependencies],
    source: str,
    query: str,
    knowledge_type: KnowledgeType,
) -> dict[str, object]:
    """Run one manual search, or say plainly that the manuals are unavailable.

    The unavailable case is reported in the result rather than raised, so the
    agent learns that this source has nothing for it and writes the note from
    what it does have, instead of retrying a tool that cannot succeed.
    """
    service = ctx.deps.knowledge_service
    if service is None:
        return {
            "source": source,
            "query": query,
            "matches": [],
            "unavailable": "No manuals are installed on this device.",
        }
    matches = await service.search(
        query,
        top_k=_KNOWLEDGE_MATCH_LIMIT,
        knowledge_type=knowledge_type,
    )
    return _search_payload(source, query, matches)


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
