"""Generate local embeddings and search the application's vector indexes."""

from __future__ import annotations

import asyncio
import threading
import typing

from pydantic_ai import Embedder

if typing.TYPE_CHECKING:
    from ntk.models.knowledge import KnowledgeType
    from ntk.models.rag import RagSearchMatch
    from ntk.repositories.embedding_repo import EmbeddingRepo

DEFAULT_EMBEDDING_MODEL = "sentence-transformers:sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

_MAX_RESULTS = 20
_INFERENCE_LOCK = threading.Lock()
_SHARED_EMBEDDER = Embedder(DEFAULT_EMBEDDING_MODEL)


class EmbeddingService:
    """Create local embeddings and search pgvector-backed content."""

    def __init__(
        self,
        repository: EmbeddingRepo | None = None,
    ) -> None:
        """Initialize local embeddings with optional vector persistence."""
        self.embedding_model = DEFAULT_EMBEDDING_MODEL
        self.embedder = _SHARED_EMBEDDER
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

    def search_assessments(
        self,
        text: str,
        top_k: int = 5,
    ) -> list[RagSearchMatch]:
        """Return assessments most similar to the supplied text."""
        self._validate_top_k(top_k)
        vector = self._embed_query(text)
        return self._repository().search_assessments(vector, top_k)

    async def search_assessments_async(
        self,
        text: str,
        top_k: int = 5,
    ) -> list[RagSearchMatch]:
        """Return similar assessments without blocking or nesting an event loop."""
        self._validate_top_k(top_k)
        vector = await asyncio.to_thread(self._embed_query, text)
        return self._repository().search_assessments(vector, top_k)

    async def search_knowledge(
        self,
        text: str,
        top_k: int = 5,
        *,
        document_type: KnowledgeType | None = None,
    ) -> list[RagSearchMatch]:
        """Return content from either or both supported knowledge manuals."""
        self._validate_top_k(top_k)
        # ``Embedder.embed_query_sync`` manages its own async runner. Calling it
        # directly from a FastAPI request therefore attempts to nest event loops.
        # Keep the synchronous local-model call off the request event loop.
        vector = await asyncio.to_thread(self._embed_query, text)
        repository = self._repository()
        if document_type is None:
            return repository.search_knowledge(vector, top_k)
        return repository.search_knowledge(
            vector,
            top_k,
            document_type=document_type,
        )

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
