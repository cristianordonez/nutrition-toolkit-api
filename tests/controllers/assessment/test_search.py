from __future__ import annotations

import typing
from uuid import uuid4

import pytest

from ntk.controllers.assessment.search import (
    AssessmentSearchController,
    AssessmentSearchOptions,
    AssessmentSearchResponse,
)


class OpenAIService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def get_embeddings(self, chunks: list[str]) -> list[list[float]]:
        self.queries.extend(chunks)
        return [[0.1, 0.2]]


class Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.parameters: tuple[object, ...] = ()
        self.statement = ""

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        self.statement = statement
        self.parameters = parameters

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class Connection:
    def __init__(self, cursor: Cursor) -> None:
        self.cursor_instance = cursor

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def cursor(self) -> Cursor:
        return self.cursor_instance


def test_assessment_search_embeds_and_filters_assessments() -> None:
    document_id = uuid4()
    cursor = Cursor([(document_id, "assessment.pdf", "ADIME", 0.91)])
    service = OpenAIService()
    controller = AssessmentSearchController(
        open_ai_service=service,  # ty: ignore[invalid-argument-type]
        connection_factory=lambda: Connection(cursor),  # ty: ignore[invalid-argument-type]
    )

    output = controller.run(
        AssessmentSearchOptions(text="  weight loss  ", top_k=3),
    )

    assert service.queries == ["weight loss"]
    assert "a.source_filename" in cursor.statement
    assert cursor.parameters == ("[0.1,0.2]", "[0.1,0.2]", 3)
    assert output.result.matches[0].document_id == document_id
    assert output.result.to_console() == "# assessment.pdf (0.9100)\nADIME"


def test_assessment_search_labels_generated_assessment_without_filename() -> None:
    cursor = Cursor([(uuid4(), None, "Generated ADIME", 0.8)])
    controller = AssessmentSearchController(
        open_ai_service=OpenAIService(),  # ty: ignore[invalid-argument-type]
        connection_factory=lambda: Connection(cursor),  # ty: ignore[invalid-argument-type]
    )

    output = controller.run(AssessmentSearchOptions(text="generated"))

    assert output.result.matches[0].filename == "generated-assessment"


def test_assessment_search_rejects_blank_text() -> None:
    controller = AssessmentSearchController(open_ai_service=OpenAIService())  # ty: ignore[invalid-argument-type]

    with pytest.raises(ValueError, match="must not be empty"):
        controller.run(AssessmentSearchOptions(text=" "))


def test_assessment_search_response_renders_no_matches() -> None:
    assert AssessmentSearchResponse(matches=[]).to_console() == ""
