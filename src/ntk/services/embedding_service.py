"""Generate local embeddings and search the application's vector indexes."""

from __future__ import annotations

import asyncio
import threading
import typing

from pydantic_ai import Embedder

if typing.TYPE_CHECKING:
    from ntk.models.rag import RagSearchMatch
    from ntk.repositories.embedding_repo import EmbeddingRepo

DEFAULT_EMBEDDING_MODEL = "sentence-transformers:sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

_MAX_RESULTS = 20
_INFERENCE_LOCK = threading.Lock()


class EmbeddingService:
    """Create local embeddings and search pgvector-backed content."""

    def __init__(
        self,
        repository: EmbeddingRepo | None = None,
    ) -> None:
        """Initialize local embeddings with optional vector persistence."""
        self.embedding_model = DEFAULT_EMBEDDING_MODEL
        self.embedder = Embedder(DEFAULT_EMBEDDING_MODEL)
        self.repository = repository

    def get_embedding(self, content: str) -> list[float]:
        """Embed one document for storage in the vector index."""
        return self.get_embeddings([content])[0]

    async def get_embedding_async(self, content: str) -> list[float]:
        """Embed one document without creating a nested event-loop boundary."""
        return (await self.get_embeddings_async([content]))[0]

    def get_embeddings(self, contents: list[str]) -> list[list[float]]:
        """Embed documents in one batch for storage in the vector index."""
        if not contents:
            return []
        if any(not content.strip() for content in contents):
            msg = "Embedding content must not be empty"
            raise ValueError(msg)
        with _INFERENCE_LOCK:
            result = self.embedder.embed_documents_sync(contents)
        return [list(embedding) for embedding in result.embeddings]

    async def get_embeddings_async(self, contents: list[str]) -> list[list[float]]:
        """Embed documents off-loop through the serialized local model."""
        return await asyncio.to_thread(self.get_embeddings, contents)

    def search_context(
        self,
        text: str,
        *,
        knowledge_top_k: int = 3,
        assessment_top_k: int = 5,
    ) -> tuple[list[RagSearchMatch], list[RagSearchMatch]]:
        """Search both indexes from one transient summary embedding."""
        self._validate_top_k(knowledge_top_k)
        self._validate_top_k(assessment_top_k)
        vector = self._embed_query(text)
        repository = self._repository()
        return (
            repository.search_knowledge(vector, knowledge_top_k),
            repository.search_assessments(vector, assessment_top_k),
        )

    def search_assessments(
        self,
        text: str,
        top_k: int = 5,
    ) -> list[RagSearchMatch]:
        """Return assessments most similar to the supplied text."""
        self._validate_top_k(top_k)
        vector = self._embed_query(text)
        return self._repository().search_assessments(vector, top_k)

    def search_knowledge(
        self,
        text: str,
        top_k: int = 5,
    ) -> list[RagSearchMatch]:
        """Return diet and nutrition manual content similar to the text."""
        self._validate_top_k(top_k)
        vector = self._embed_query(text)
        return self._repository().search_knowledge(vector, top_k)

    def _embed_query(self, text: str) -> str:
        query = text.strip()
        if not query:
            msg = "Search text must not be empty"
            raise ValueError(msg)
        with _INFERENCE_LOCK:
            result = self.embedder.embed_query_sync(query)
        embedding = result.embeddings[0]
        return "[" + ",".join(str(value) for value in embedding) + "]"

    @staticmethod
    def _validate_top_k(top_k: int) -> None:
        if not 1 <= top_k <= _MAX_RESULTS:
            msg = "top_k must be between 1 and 20"
            raise ValueError(msg)

    def _repository(self) -> EmbeddingRepo:
        if self.repository is None:
            msg = "An embedding repository is required for vector search"
            raise RuntimeError(msg)
        return self.repository
