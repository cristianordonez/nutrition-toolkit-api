"""Search one person's previously generated Nutrition Care Processes."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from api.controllers.session import controller_session
from api.models.rag import RagSearchMatch  # noqa: TC001 - required by Pydantic
from api.repositories.embedding_repo import EmbeddingRepo
from api.services.embedding_service import EmbeddingService
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPSearchOptions(BaseModel):
    """Options for searching one person's previously generated ncps."""

    text: str = Field(description="Text to search for")
    person_identifier: str = Field(description="The person's external identifier")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of matches")


class NCPSearchResponse(ConsoleRenderableModel):
    """Nutrition Care Process chunks matching a semantic search."""

    matches: list[RagSearchMatch]

    def to_console(self) -> str:
        """Render matching filenames and chunk content."""
        return "\n\n".join(
            f"# {match.filename} ({match.similarity:.4f})\n{match.chunk_text}"
            for match in self.matches
        )


class NCPSearchController(BaseController):
    """Search ncp embeddings by semantic similarity."""

    name = "search"
    help = "Search one person's previously generated Nutrition Care Processes"
    options_model = NCPSearchOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def search(
        self,
        text: str,
        person_identifier: str,
        top_k: int = 5,
    ) -> Output[NCPSearchResponse]:
        """Build search options and run the ncp search workflow."""
        with controller_session(self.session) as session:
            service = EmbeddingService(EmbeddingRepo(session))
            matches = await service.search_ncps_async(text, person_identifier, top_k)
        return self._output(matches)

    def run(
        self,
        options: NCPSearchOptions,
    ) -> Output[NCPSearchResponse]:
        """Embed the query and return matching ncp chunks."""
        with controller_session(self.session) as session:
            service = EmbeddingService(EmbeddingRepo(session))
            matches = service.search_ncps(
                options.text,
                options.person_identifier,
                options.top_k,
            )
        return self._output(matches)

    def _output(
        self,
        matches: list[RagSearchMatch],
    ) -> Output[NCPSearchResponse]:
        """Build the shared controller output for sync and async callers."""
        return Output(
            result=NCPSearchResponse(matches=matches),
            controller=self.name,
            exit_code=0,
        )
