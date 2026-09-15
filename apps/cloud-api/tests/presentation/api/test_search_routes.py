from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

from api.controllers.knowledge.search import (
    KnowledgeSearchOptions,
    KnowledgeSearchResponse,
)
from api.controllers.ncp.search import NCPSearchOptions
from api.models.rag import RagSearchMatch
from api.presentation.api.routers import knowledge, nutrition_care_processes

if typing.TYPE_CHECKING:
    import pytest


def test_search_routes_use_matching_application_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=42,
        filename="document.pdf",
        chunk_text="Nutrition",
        similarity=0.9,
    )

    class EmbeddingRepo:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class EmbeddingService:
        def __init__(self, repository: EmbeddingRepo) -> None:
            assert isinstance(repository, EmbeddingRepo)

        @staticmethod
        async def search_ncps_async(
            text: str,
            person_identifier: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == "weight loss"
            assert person_identifier == "R1"
            assert top_k == 5  # noqa: PLR2004
            return [match]

    class KnowledgeController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def run(options: KnowledgeSearchOptions) -> object:
            assert options.text == "protein needs"
            return SimpleNamespace(result=KnowledgeSearchResponse(matches=[match]))

    monkeypatch.setattr(nutrition_care_processes, "EmbeddingRepo", EmbeddingRepo)
    monkeypatch.setattr(
        nutrition_care_processes,
        "EmbeddingService",
        EmbeddingService,
    )
    monkeypatch.setattr(
        knowledge,
        "KnowledgeVectorSearchController",
        KnowledgeController,
    )

    assert asyncio.run(
        nutrition_care_processes.search_ncps(
            NCPSearchOptions(text="weight loss", person_identifier="R1"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    ) == [match]
    assert asyncio.run(
        knowledge.search_knowledge(
            KnowledgeSearchOptions(text="protein needs"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    ) == [match]
