"""Search persisted clinical nutrition knowledge vectors."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.rag import RagSearchMatch  # noqa: TC001 - required by Pydantic
from ntk.repositories.embedding_repo import EmbeddingRepo
from ntk.services.embedding_service import EmbeddingService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class KnowledgeSearchOptions(BaseModel):
    """Options for searching clinical nutrition knowledge."""

    text: str = Field(description="Text to search for")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of matches")


class KnowledgeSearchResponse(ConsoleRenderableModel):
    """Clinical knowledge chunks matching a semantic search."""

    matches: list[RagSearchMatch]

    def to_console(self) -> str:
        """Render matching filenames and chunk content."""
        return "\n\n".join(
            f"# {match.filename} ({match.similarity:.4f})\n{match.chunk_text}"
            for match in self.matches
        )


class KnowledgeVectorSearchController(BaseController):
    """Search knowledge embeddings by semantic similarity."""

    name = "knowledge"
    help = "Search clinical nutrition knowledge vectors"
    options_model = KnowledgeSearchOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: KnowledgeSearchOptions,
    ) -> Output[KnowledgeSearchResponse]:
        """Embed the query and return matching knowledge chunks."""
        with controller_session(self.session) as session:
            service = EmbeddingService(EmbeddingRepo(session))
            matches = service.search_knowledge(options.text, options.top_k)
        return Output(
            result=KnowledgeSearchResponse(matches=matches),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "KnowledgeSearchOptions",
    "KnowledgeSearchResponse",
    "KnowledgeVectorSearchController",
]
