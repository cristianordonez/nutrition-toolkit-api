from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

from ntk.controllers.search.assessment import (
    AssessmentSearchOptions,
    AssessmentSearchResponse,
)
from ntk.controllers.search.knowledge import (
    KnowledgeSearchOptions,
    KnowledgeSearchResponse,
)
from ntk.models.rag import RagSearchMatch
from ntk.presentation.api.routers import search

if typing.TYPE_CHECKING:
    import pytest


def test_search_routes_use_matching_controllers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=42,
        filename="document.pdf",
        chunk_text="Nutrition",
        similarity=0.9,
    )

    class AssessmentController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: AssessmentSearchOptions) -> object:
            assert options.text == "weight loss"
            return SimpleNamespace(result=AssessmentSearchResponse(matches=[match]))

    class KnowledgeController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: KnowledgeSearchOptions) -> object:
            assert options.text == "protein needs"
            return SimpleNamespace(result=KnowledgeSearchResponse(matches=[match]))

    monkeypatch.setattr(search, "AssessmentSearchController", AssessmentController)
    monkeypatch.setattr(
        search,
        "KnowledgeVectorSearchController",
        KnowledgeController,
    )

    assert asyncio.run(
        search.search_assessments(
            AssessmentSearchOptions(text="weight loss"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    ) == [match]
    assert asyncio.run(
        search.search_knowledge(
            KnowledgeSearchOptions(text="protein needs"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    ) == [match]
