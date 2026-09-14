from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

from ntk.controllers.knowledge.search import (
    KnowledgeSearchOptions,
    KnowledgeSearchResponse,
)
from ntk.controllers.ncp.search import (
    NCPSearchOptions,
)
from ntk.models.rag import RagSearchMatch
from ntk.presentation.api.routers import knowledge, nutrition_care_processes

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

    class ClinicalNoteRepository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class NutritionCareProcessService:
        def __init__(self, repository: ClinicalNoteRepository) -> None:
            assert isinstance(repository, ClinicalNoteRepository)

        @staticmethod
        async def search_ncps_async(
            text: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == "weight loss"
            assert top_k == 5  # noqa: PLR2004
            return [match]

    class KnowledgeController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def run(options: KnowledgeSearchOptions) -> object:
            assert options.text == "protein needs"
            return SimpleNamespace(result=KnowledgeSearchResponse(matches=[match]))

    monkeypatch.setattr(
        nutrition_care_processes,
        "EmbeddingRepo",
        ClinicalNoteRepository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "EmbeddingService",
        NutritionCareProcessService,
    )
    monkeypatch.setattr(
        knowledge,
        "KnowledgeVectorSearchController",
        KnowledgeController,
    )

    assert asyncio.run(
        nutrition_care_processes.search_ncps(
            NCPSearchOptions(text="weight loss"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    ) == [match]
    assert asyncio.run(
        knowledge.search_knowledge(
            KnowledgeSearchOptions(text="protein needs"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    ) == [match]
