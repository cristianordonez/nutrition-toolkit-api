from __future__ import annotations

import typing
from uuid import uuid4

import pytest

from ntk.controllers.knowledge.search import (
    KnowledgeSearchController,
    KnowledgeSearchOptions,
    KnowledgeSearchResponse,
)


class OpenAIService:
    def get_embeddings(self, chunks: list[str]) -> list[list[float]]:
        assert chunks == ["protein needs"]
        return [[0.1, 0.2]]


class Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.parameters: tuple[object, ...] = ()

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def execute(self, _: str, parameters: tuple[object, ...]) -> None:
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


def test_knowledge_search_queries_both_manual_types() -> None:
    document_id = uuid4()
    cursor = Cursor([(document_id, "manual.pdf", "Guidance", 0.91)])
    controller = KnowledgeSearchController(
        open_ai_service=OpenAIService(),  # ty: ignore[invalid-argument-type]
        connection_factory=lambda: Connection(cursor),  # ty: ignore[invalid-argument-type]
    )

    output = controller.run(KnowledgeSearchOptions(text=" protein needs ", top_k=3))

    assert cursor.parameters == (
        "[0.1,0.2]",
        "diet-manual",
        "nutrition-care-manual",
        "[0.1,0.2]",
        3,
    )
    assert output.result.matches[0].document_id == document_id
    assert output.result.to_console() == "# manual.pdf (0.9100)\nGuidance"


def test_knowledge_search_rejects_blank_text() -> None:
    controller = KnowledgeSearchController(open_ai_service=OpenAIService())  # ty: ignore[invalid-argument-type]

    with pytest.raises(ValueError, match="must not be empty"):
        controller.run(KnowledgeSearchOptions(text=" "))


def test_knowledge_search_response_renders_no_matches() -> None:
    assert KnowledgeSearchResponse(matches=[]).to_console() == ""
