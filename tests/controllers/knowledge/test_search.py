from __future__ import annotations

import asyncio
import typing

from ntk.controllers.knowledge import search as knowledge
from ntk.controllers.knowledge.search import (
    KnowledgeSearchOptions,
    KnowledgeSearchResponse,
    KnowledgeVectorSearchController,
)
from ntk.models.knowledge import KnowledgeType
from ntk.models.rag import RagSearchMatch

if typing.TYPE_CHECKING:
    import pytest


def test_knowledge_vector_search_uses_embedding_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=1,
        filename="manual.pdf",
        chunk_text="Protein guidance",
        similarity=0.9,
        knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
        section_title="Protein Requirements",
        source_page_start=12,
        source_page_end=13,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        async def search_knowledge(
            text: str,
            top_k: int,
            *,
            document_type: KnowledgeType | None,
        ) -> list[RagSearchMatch]:
            assert text == "protein needs"
            assert top_k == 3  # noqa: PLR2004
            assert document_type is None
            return [match]

    monkeypatch.setattr(knowledge, "EmbeddingRepo", Repository)
    monkeypatch.setattr(knowledge, "EmbeddingService", Service)

    output = asyncio.run(
        KnowledgeVectorSearchController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(KnowledgeSearchOptions(text="protein needs", top_k=3)),
    )

    assert output.result.matches == [match]
    assert output.result.to_console() == (
        "# manual.pdf | Protein Requirements | page 12-13 (0.9000)\nProtein guidance"
    )


def test_knowledge_search_response_handles_single_page() -> None:
    response = KnowledgeSearchResponse(
        matches=[
            RagSearchMatch(
                document_id=1,
                filename="manual.pdf",
                chunk_text="Diet guidance",
                similarity=0.8,
                section_title="Renal Diet",
                source_page_start=22,
                source_page_end=22,
            ),
        ],
    )

    assert "page 22" in response.to_console()
    assert "page 22-22" not in response.to_console()
