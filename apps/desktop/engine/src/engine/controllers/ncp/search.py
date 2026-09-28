"""Search stored NCP style examples by semantic similarity."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.database.sessions import controller_session
from engine.models.base import ConsoleRenderableModel
from engine.models.ncp_note import NCPNoteType  # noqa: TC001
from engine.models.output import Output
from engine.models.rag import RagSearchMatch  # noqa: TC001
from engine.services.embedding_service import EmbeddingService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPSearchOptions(BaseModel):
    """Options for searching NCP style examples."""

    text: str = Field(description="Text to search for")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of matches")
    note_type: NCPNoteType | None = Field(
        default=None,
        description="Only search examples of this NCP note type, or all if excluded.",
    )


class NCPSearchResponse(ConsoleRenderableModel):
    """NCP style examples matching a semantic search."""

    matches: list[RagSearchMatch]

    def to_console(self) -> str:
        """Render each matching note with its type, id and similarity."""
        return "\n\n".join(
            f"# {match.filename} | note {match.document_id} "
            f"({match.similarity:.4f})\n{match.chunk_text}"
            for match in self.matches
        )


class NCPVectorSearchController(BaseController):
    """Search NCP example embeddings by semantic similarity."""

    name = "search"
    help = "Search NCP style example vectors"
    options_model = NCPSearchOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(self, options: NCPSearchOptions) -> Output[NCPSearchResponse]:
        """Embed the query and return the nearest NCP examples."""
        with controller_session(self.session) as session:
            matches = await EmbeddingService(session).search_examples_async(
                options.text,
                options.top_k,
                note_type=options.note_type,
            )
        return Output(
            result=NCPSearchResponse(matches=matches),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "NCPSearchOptions",
    "NCPSearchResponse",
    "NCPVectorSearchController",
]
