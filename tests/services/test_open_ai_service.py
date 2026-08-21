from __future__ import annotations

from types import SimpleNamespace

import pytest

from ntk.services.open_ai_service import OpenAIService


class FakeEmbeddings:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.calls: list[tuple[str, str]] = []

    def create(self, *, input: str, model: str) -> object:  # noqa: A002
        self.calls.append((input, model))
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.vector)])


class FakeOpenAI:
    def __init__(self, vector: list[float]) -> None:
        self.embeddings = FakeEmbeddings(vector)


class EmptyEmbeddings:
    def create(self, *, input: str, model: str) -> object:  # noqa: A002
        del input, model
        return SimpleNamespace(data=[])


class EmptyOpenAI:
    def __init__(self) -> None:
        self.embeddings = EmptyEmbeddings()


def test_create_embedding_uses_configured_model() -> None:
    client = FakeOpenAI([0.1, 0.2])
    service = OpenAIService(
        client=client,  # ty: ignore[invalid-argument-type]
        embedding_model="embedding-model",
    )

    vector = service.create_embedding("Nutrition assessment")

    assert vector == [0.1, 0.2]
    assert client.embeddings.calls == [("Nutrition assessment", "embedding-model")]


def test_create_embedding_rejects_empty_provider_response() -> None:
    service = OpenAIService(
        client=EmptyOpenAI(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(RuntimeError, match="no embedding vector"):
        service.create_embedding("Nutrition assessment")
