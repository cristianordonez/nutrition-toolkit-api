from __future__ import annotations

import asyncio

import pytest

from ntk.controllers.assessment import search
from ntk.controllers.assessment.search import (
    AssessmentSearchController,
    AssessmentSearchOptions,
    AssessmentSearchResponse,
)
from ntk.models.rag import RagSearchMatch


def test_assessment_search_embeds_and_filters_assessments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = 42
    match = RagSearchMatch(
        document_id=document_id,
        filename="assessment.pdf",
        chunk_text="ADIME",
        similarity=0.91,
    )

    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def search_assessments(self, text: str, top_k: int) -> list[RagSearchMatch]:
            assert text == "  weight loss  "
            assert top_k == 3  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = AssessmentSearchController(session=object())  # ty: ignore[invalid-argument-type]

    output = controller.run(
        AssessmentSearchOptions(text="  weight loss  ", top_k=3),
    )

    assert output.result.matches[0].document_id == document_id
    assert output.result.to_console() == "# assessment.pdf (0.9100)\nADIME"


def test_assessment_search_labels_generated_assessment_without_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=43,
        filename="generated-assessment",
        chunk_text="Generated ADIME",
        similarity=0.8,
    )

    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def search_assessments(self, text: str, top_k: int) -> list[RagSearchMatch]:
            assert text == "generated"
            assert top_k == 5  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = AssessmentSearchController(session=object())  # ty: ignore[invalid-argument-type]

    output = controller.run(AssessmentSearchOptions(text="generated"))

    assert output.result.matches[0].filename == "generated-assessment"


def test_assessment_search_async_entry_point_uses_async_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=44,
        filename="assessment.pdf",
        chunk_text="ADIME",
        similarity=0.75,
    )

    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        @staticmethod
        async def search_assessments_async(
            text: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == "weight loss"
            assert top_k == 2  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = AssessmentSearchController(session=object())  # ty: ignore[invalid-argument-type]

    output = asyncio.run(controller.search("weight loss", top_k=2))

    assert output.result.matches == [match]


def test_assessment_search_rejects_blank_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def search_assessments(self, text: str, top_k: int) -> list[RagSearchMatch]:
            assert text == " "
            assert top_k == 5  # noqa: PLR2004
            message = "Search text must not be empty"
            raise ValueError(message)

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = AssessmentSearchController(session=object())  # ty: ignore[invalid-argument-type]

    with pytest.raises(ValueError, match="must not be empty"):
        controller.run(AssessmentSearchOptions(text=" "))


def test_assessment_search_response_renders_no_matches() -> None:
    assert AssessmentSearchResponse(matches=[]).to_console() == ""
