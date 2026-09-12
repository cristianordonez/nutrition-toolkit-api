from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ntk.models.knowledge import KnowledgeType
from ntk.models.rag import RagSearchMatch
from ntk.services.embedding_service import EmbeddingService


class Embedder:
    def __init__(self) -> None:
        self.document_batches: list[list[str]] = []
        self.queries: list[str] = []
        self.query_called_from_event_loop: bool | None = None

    def embed_documents_sync(self, contents: list[str]) -> object:
        self.document_batches.append(contents)
        return SimpleNamespace(
            embeddings=[[float(index)] for index, _ in enumerate(contents)],
        )

    async def embed_documents(self, contents: list[str]) -> object:
        self.document_batches.append(contents)
        return SimpleNamespace(
            embeddings=[[float(index)] for index, _ in enumerate(contents)],
        )

    def embed_query_sync(self, query: str) -> object:
        self.queries.append(query)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.query_called_from_event_loop = False
        else:
            self.query_called_from_event_loop = True
        return SimpleNamespace(embeddings=[[0.1, 0.2]])


class Repository:
    def __init__(self, matches: list[RagSearchMatch]) -> None:
        self.matches = matches
        self.assessment_args: tuple[str, int] | None = None
        self.knowledge_args: tuple[str, int] | None = None
        self.knowledge_type: KnowledgeType | None = None

    def search_assessments(self, vector: str, top_k: int) -> list[RagSearchMatch]:
        self.assessment_args = vector, top_k
        return self.matches

    def search_knowledge(
        self,
        vector: str,
        top_k: int,
        *,
        document_type: KnowledgeType | None = None,
    ) -> list[RagSearchMatch]:
        self.knowledge_type = document_type
        self.knowledge_args = vector, top_k
        return self.matches


def _service(
    matches: list[RagSearchMatch] | None = None,
) -> tuple[EmbeddingService, Embedder, Repository]:
    embedder = Embedder()
    repository = Repository(matches or [])
    service = EmbeddingService(repository)  # ty: ignore[invalid-argument-type]
    service.embedder = embedder  # ty: ignore[invalid-assignment]
    return service, embedder, repository


def test_embedding_services_reuse_the_loaded_model() -> None:
    first = EmbeddingService()
    second = EmbeddingService()

    assert first.embedder is second.embedder


def test_embeds_documents_in_one_batch() -> None:
    service, embedder, _ = _service()

    embeddings = service.get_embeddings(["assessment", "knowledge"])

    assert embeddings == [[0.0], [1.0]]
    assert embedder.document_batches == [["assessment", "knowledge"]]


def test_embeds_documents_inside_running_event_loop() -> None:
    service, embedder, _ = _service()

    async def embed() -> list[list[float]]:
        return await service.get_embeddings_async(["assessment", "knowledge"])

    embeddings = asyncio.run(embed())

    assert embeddings == [[0.0], [1.0]]
    assert embedder.document_batches == [["assessment", "knowledge"]]


def test_search_assessments_uses_query_embedding() -> None:
    document_id = 1
    match = RagSearchMatch(
        document_id=document_id,
        filename="assessment.pdf",
        chunk_text="ADIME",
        similarity=0.91,
    )
    service, embedder, repository = _service([match])

    matches = service.search_assessments("  weight loss  ", top_k=3)

    assert embedder.queries == ["weight loss"]
    assert repository.assessment_args == ("[0.1,0.2]", 3)
    assert matches[0].document_id == document_id
    assert matches[0].filename == "assessment.pdf"


def test_search_assessments_inside_running_event_loop() -> None:
    service, embedder, repository = _service()

    matches = asyncio.run(
        service.search_assessments_async("weight loss", top_k=3),
    )

    assert matches == []
    assert embedder.queries == ["weight loss"]
    assert embedder.query_called_from_event_loop is False
    assert repository.assessment_args == ("[0.1,0.2]", 3)


def test_search_knowledge_queries_both_manual_types() -> None:
    match = RagSearchMatch(
        document_id=2,
        filename="manual.pdf",
        chunk_text="Guidance",
        similarity=0.91,
    )
    service, embedder, repository = _service([match])

    matches = asyncio.run(service.search_knowledge(" protein needs ", top_k=3))

    assert embedder.queries == ["protein needs"]
    assert embedder.query_called_from_event_loop is False
    assert repository.knowledge_args == ("[0.1,0.2]", 3)
    assert matches[0].chunk_text == "Guidance"


def test_search_knowledge_filters_one_manual_type() -> None:
    service, embedder, repository = _service()

    asyncio.run(
        service.search_knowledge(
            "renal diet",
            top_k=2,
            document_type=KnowledgeType.DIET_MANUAL,
        ),
    )

    assert embedder.queries == ["renal diet"]
    assert repository.knowledge_args == ("[0.1,0.2]", 2)
    assert repository.knowledge_type is KnowledgeType.DIET_MANUAL


@pytest.mark.parametrize("text", ["", " "])
def test_search_rejects_blank_text(text: str) -> None:
    service, _, _ = _service()

    with pytest.raises(ValueError, match="must not be empty"):
        service.search_assessments(text)


@pytest.mark.parametrize("top_k", [0, 21])
def test_search_rejects_out_of_range_top_k(top_k: int) -> None:
    service, _, _ = _service()

    with pytest.raises(ValueError, match="between 1 and 20"):
        asyncio.run(service.search_knowledge("protein", top_k=top_k))
