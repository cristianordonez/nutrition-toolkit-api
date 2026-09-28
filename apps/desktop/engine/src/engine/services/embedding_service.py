"""Generate local embeddings and search the device's vector indexes.

The same shape as the server's service, and deliberately so: one embedding
model, loaded once, shared by every caller. There is no hosted embedding path
and no provider switch. The model is small enough to run on any machine the
app installs on, which makes embeddings the one part of the pipeline that is
always on-device regardless of where note generation runs.

Keeping it single-model is not only simplicity. A vector is comparable only to
others produced by the same model, so a provider switch used to silently
invalidate every stored vector and every shipped one -- including the
embeddings inside the bundled reference database, which are built once at
release time and cannot be rebuilt per user.

Vectors live in Alembic-managed sqlite-vec tables. Repositories own their
writes and nearest-neighbor queries; this service owns model inference.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import typing

from engine.database.vectors import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from engine.paths import bundled_embedding_model_dir
from engine.repositories.knowledge_repo import KnowledgeRepo
from engine.repositories.ncp_note_repo import NCPNoteRepo

if typing.TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer
    from sqlmodel import Session

    from engine.models.ncp_note import NCPNoteType
    from engine.models.rag import RagSearchMatch
    from engine.models.sql.knowledge import KnowledgeType

logger = logging.getLogger(__name__)

#: The one embedding model, matching the server's so that content embedded by
#: either is comparable. This is metadata, never a runtime download target.
DEFAULT_EMBEDDING_MODEL = EMBEDDING_MODEL

_MAX_RESULTS = 20

#: Notes are long; embedding models are not. Only the opening of a note is
#: embedded, which is where the assessment and its framing sit.
_MAX_CHARS = 8_000

#: The model is not thread-safe and is expensive to hold twice, so one instance
#: is shared and calls into it are serialized. Construction is lazy -- the
#: weights load on first use, not at import, which matters because the desktop
#: shell starts a fresh engine process for every command.
_INFERENCE_LOCK = threading.Lock()
_SHARED_MODEL: SentenceTransformer | None = None


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding model cannot be loaded or run."""


def _get_model() -> SentenceTransformer:
    """Load once while holding ``_INFERENCE_LOCK``; never download weights."""
    global _SHARED_MODEL  # noqa: PLW0603 - one process-wide model
    if _SHARED_MODEL is None:
        # Validate before importing torch, so missing bundles fail quickly.
        directory = bundled_embedding_model_dir()
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        model = SentenceTransformer(
            str(directory),
            local_files_only=True,
            trust_remote_code=False,
            token=False,
        )
        if model.get_embedding_dimension() != EMBEDDING_DIMENSIONS:
            msg = f"Bundled MiniLM must produce {EMBEDDING_DIMENSIONS} dimensions"
            raise EmbeddingUnavailableError(msg)
        _SHARED_MODEL = model
    return _SHARED_MODEL


class EmbeddingService:
    """Create embeddings and search the vector indexes built from them."""

    def __init__(self, session: Session) -> None:
        """Initialize with a facts-database session."""
        self.session = session
        self.notes = NCPNoteRepo(session)
        self.embedding_model = DEFAULT_EMBEDDING_MODEL

    @property
    def model(self) -> str:
        """The embedding model every vector in this database was built with."""
        return self.embedding_model

    def get_embedding(self, content: str) -> list[float]:
        """Embed one document for storage in a vector index."""
        return self.get_embeddings([content])[0]

    async def get_embedding_async(self, content: str) -> list[float]:
        """Embed one document without creating a nested event-loop boundary."""
        return (await self.get_embeddings_async([content]))[0]

    def get_embeddings(self, contents: list[str]) -> list[list[float]]:
        """Embed documents in one batch for storage in a vector index."""
        if not contents:
            return []
        if any(not content.strip() for content in contents):
            msg = "Embedding content must not be empty"
            raise ValueError(msg)
        trimmed = [content[:_MAX_CHARS] for content in contents]
        # Preserve the previous adapter's flag; MiniLM's bundled Normalize
        # module already normalizes outputs. Do not normalize a second time.
        try:
            with _INFERENCE_LOCK:
                result = _get_model().encode_document(
                    trimmed,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    convert_to_tensor=False,
                    normalize_embeddings=False,
                )
        except Exception as error:  # any failure to load or run means "no model"
            msg = f"{_UNAVAILABLE_MESSAGE} {error}"
            raise EmbeddingUnavailableError(msg) from error
        return result.tolist()

    async def get_embeddings_async(self, contents: list[str]) -> list[list[float]]:
        """Embed documents off-loop through the serialized local model."""
        return await asyncio.to_thread(self.get_embeddings, contents)

    async def index_examples(self, *, limit: int | None = None) -> int:
        """Embed NCP examples that have no embedding yet.

        Incremental by design: an app update can add examples at any time, and
        re-embedding what is already indexed would produce the same vector.
        Returns how many were added.
        """
        pending = self.notes.unembedded_examples(self.embedding_model, limit=limit)
        if not pending:
            return 0
        vectors = await self.get_embeddings_async(
            [note.content for note in pending],
        )
        self.notes.store_embeddings(pending, vectors, self.embedding_model)
        self.session.commit()
        return len(pending)

    def search_examples(
        self,
        text: str,
        top_k: int = 5,
    ) -> list[RagSearchMatch]:
        """Return explicit NCP style examples nearest the supplied text."""
        self._validate_top_k(top_k)
        if not self.notes.has_example_embeddings(self.embedding_model):
            return []
        vector = self._embed_query(text)
        return self.notes.search_examples(vector, top_k, self.embedding_model)

    async def search_examples_async(
        self,
        text: str,
        top_k: int = 5,
        *,
        note_type: NCPNoteType | None = None,
    ) -> list[RagSearchMatch]:
        """Return similar NCP examples without blocking the event loop."""
        self._validate_top_k(top_k)
        if not self.notes.has_example_embeddings(self.embedding_model):
            return []
        vector = await asyncio.to_thread(self._embed_query, text)
        return self.notes.search_examples(
            vector,
            top_k,
            self.embedding_model,
            note_type=note_type,
        )

    async def search_knowledge(
        self,
        text: str,
        top_k: int = 5,
        *,
        document_type: KnowledgeType | None = None,
    ) -> list[RagSearchMatch]:
        """Return content from either or both supported knowledge manuals."""
        self._validate_top_k(top_k)
        # Keep local inference off the event loop, like document embedding.
        text = text.strip()
        vector = await asyncio.to_thread(self._embed_query, text)
        repository = KnowledgeRepo(self.session, self.embedding_model)
        return repository.search(vector, top_k, knowledge_type=document_type)

    def _embed_query(self, text: str) -> list[float]:
        """Embed one search query, rejecting empty text."""
        query = text.strip()
        if not query:
            msg = "Search text must not be empty"
            raise ValueError(msg)
        try:
            with _INFERENCE_LOCK:
                result = _get_model().encode_query(
                    [query[:_MAX_CHARS]],
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    convert_to_tensor=False,
                    normalize_embeddings=False,
                )
        except Exception as error:  # any failure to load or run means "no model"
            msg = f"{_UNAVAILABLE_MESSAGE} {error}"
            raise EmbeddingUnavailableError(msg) from error
        return result[0].tolist()

    @staticmethod
    def _validate_top_k(top_k: int) -> None:
        if not 1 <= top_k <= _MAX_RESULTS:
            msg = f"top_k must be between 1 and {_MAX_RESULTS}"
            raise ValueError(msg)


_UNAVAILABLE_MESSAGE = (
    f"Could not run the embedding model {DEFAULT_EMBEDDING_MODEL}. Retrieval is "
    "unavailable until it can be loaded."
)


__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "EmbeddingService",
    "EmbeddingUnavailableError",
]
