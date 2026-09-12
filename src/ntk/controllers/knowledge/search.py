"""Search persisted clinical nutrition knowledge vectors."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models import KnowledgeType  # noqa: TC001 - required by Pydantic
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
    document_type: KnowledgeType | None = Field(
        default=None,
        description="Either nutrition-care-manual or diet-manual, or both if excluded.",
    )


class KnowledgeSearchResponse(ConsoleRenderableModel):
    """Clinical knowledge chunks matching a semantic search."""

    matches: list[RagSearchMatch]

    def to_console(self) -> str:
        """Render matching filenames and chunk content."""
        return "\n\n".join(self._render_match(match) for match in self.matches)

    @staticmethod
    def _render_match(match: RagSearchMatch) -> str:
        """Render one match with its available section and page provenance."""
        metadata = [match.filename]
        if match.section_title:
            metadata.append(match.section_title)
        if match.source_page_start is not None:
            page = str(match.source_page_start)
            if match.source_page_end != match.source_page_start:
                page = f"{page}-{match.source_page_end}"
            metadata.append(f"page {page}")
        return f"# {' | '.join(metadata)} ({match.similarity:.4f})\n{match.chunk_text}"


class KnowledgeVectorSearchController(BaseController):
    """Search knowledge embeddings by semantic similarity."""

    name = "search"
    help = "Search clinical nutrition knowledge vectors"
    options_model = KnowledgeSearchOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: KnowledgeSearchOptions,
    ) -> Output[KnowledgeSearchResponse]:
        """Embed the query and return matching knowledge chunks."""
        with controller_session(self.session) as session:
            service = EmbeddingService(EmbeddingRepo(session))
            matches = await service.search_knowledge(
                options.text,
                options.top_k,
                document_type=options.document_type,
            )
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
