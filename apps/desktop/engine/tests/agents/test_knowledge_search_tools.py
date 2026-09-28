from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

from engine.agents.tools.knowledge_search_tools import (
    KnowledgeSearchToolDependencies,
    RagSearchInput,
    get_knowledge_from_diet_manual,
)
from engine.models.rag import RagSearchMatch
from engine.models.sql.knowledge import KnowledgeType


class _Knowledge:
    """Stands in for the embedding service's knowledge-base search."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, KnowledgeType | None]] = []

    async def search_knowledge(
        self,
        text: str,
        top_k: int = 5,
        *,
        document_type: KnowledgeType | None = None,
    ) -> list[RagSearchMatch]:
        self.calls.append((text, top_k, document_type))
        return [
            RagSearchMatch(
                document_id=1,
                filename="NCM2026_DietManual.pdf",
                chunk_text="A renal diet limits potassium.",
                similarity=0.8,
            ),
        ]


def _run(service: object) -> dict[str, object]:
    ctx = SimpleNamespace(
        deps=KnowledgeSearchToolDependencies(
            knowledge_service=typing.cast("typing.Any", service),
        ),
    )
    return asyncio.run(
        get_knowledge_from_diet_manual(
            typing.cast("typing.Any", ctx),
            RagSearchInput(query="  renal diet  "),
        ),
    )


def test_manual_lookup_searches_the_selected_manual() -> None:
    knowledge = _Knowledge()

    result = _run(knowledge)

    assert knowledge.calls == [("renal diet", 5, KnowledgeType.DIET_MANUAL)]
    assert result["source"] == "diet-manual"
    assert result["matches"] == [
        {
            "document_id": 1,
            "filename": "NCM2026_DietManual.pdf",
            "chunk_text": "A renal diet limits potassium.",
            "similarity": 0.8,
            "knowledge_type": None,
            "section_title": None,
            "source_page_start": None,
            "source_page_end": None,
        },
    ]


def test_manual_lookup_without_a_knowledge_base_says_so() -> None:
    result = _run(None)

    assert result["matches"] == []
    assert "unavailable" in result
