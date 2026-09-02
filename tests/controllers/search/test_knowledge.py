from __future__ import annotations

import typing

from ntk.controllers.search import knowledge
from ntk.controllers.search.knowledge import (
    KnowledgeSearchOptions,
    KnowledgeVectorSearchController,
)
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
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        def search_knowledge(text: str, top_k: int) -> list[RagSearchMatch]:
            assert text == "protein needs"
            assert top_k == 3  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(knowledge, "EmbeddingRepo", Repository)
    monkeypatch.setattr(knowledge, "EmbeddingService", Service)

    output = KnowledgeVectorSearchController(
        session="session",  # ty: ignore[invalid-argument-type]
    ).run(KnowledgeSearchOptions(text="protein needs", top_k=3))

    assert output.result.matches == [match]
