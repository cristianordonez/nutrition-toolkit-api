"""Search previously ingested nutrition assessments."""

from __future__ import annotations

import typing
from importlib import import_module

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.rag import RagSearchMatch
from ntk.models.settings import SETTINGS
from ntk.services.open_ai_service import OpenAIService

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from psycopg import Connection

_SEARCH_SQL = """
    SELECT a.id, a.source_filename, a.content,
           1 - (e.embedding_vector <=> %s::vector) AS similarity
    FROM assessment_embeddings e
    JOIN assessment a ON a.id = e.assessment_id
    ORDER BY e.embedding_vector <=> %s::vector
    LIMIT %s
"""


class AssessmentSearchOptions(BaseModel):
    """Options for searching previously ingested assessments."""

    text: str = Field(description="Text to search for")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of matches")


class AssessmentSearchResponse(ConsoleRenderableModel):
    """Assessment chunks matching a semantic search."""

    matches: list[RagSearchMatch]

    def to_console(self) -> str:
        """Render matching filenames and chunk content."""
        return "\n\n".join(
            f"# {match.filename} ({match.similarity:.4f})\n{match.chunk_text}"
            for match in self.matches
        )


class AssessmentSearchController(BaseController):
    """Search assessment embeddings by semantic similarity."""

    name = "search"
    help = "Search previously ingested nutrition assessments"
    options_model = AssessmentSearchOptions

    def __init__(
        self,
        open_ai_service: OpenAIService | None = None,
        connection_factory: Callable[[], Connection[tuple[object, ...]]] | None = None,
    ) -> None:
        """Initialize optional search dependencies."""
        self.open_ai_service = open_ai_service
        self.connection_factory = connection_factory

    async def search(
        self,
        text: str,
        top_k: int = 5,
    ) -> Output[AssessmentSearchResponse]:
        """Build search options and run the assessment search workflow."""
        return self.run(AssessmentSearchOptions(text=text, top_k=top_k))

    def run(
        self,
        options: AssessmentSearchOptions,
    ) -> Output[AssessmentSearchResponse]:
        """Embed the query and return matching assessment chunks."""
        query = options.text.strip()
        if not query:
            msg = "Search text must not be empty"
            raise ValueError(msg)
        service = self.open_ai_service or OpenAIService()
        embedding = service.get_embeddings([query])[0]
        vector = "[" + ",".join(str(value) for value in embedding) + "]"
        connect = self.connection_factory or self._connect
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                _SEARCH_SQL,
                (
                    vector,
                    vector,
                    options.top_k,
                ),
            )
            rows = cursor.fetchall()
        matches = [
            RagSearchMatch(
                document_id=typing.cast("UUID", row[0]),
                filename=str(row[1] or "generated-assessment"),
                chunk_text=str(row[2]),
                similarity=float(str(row[3])),
            )
            for row in rows
        ]
        return Output(
            result=AssessmentSearchResponse(matches=matches),
            controller=self.name,
            exit_code=0,
        )

    @staticmethod
    def _connect() -> Connection[tuple[object, ...]]:
        """Open a database connection for vector search."""
        connect = import_module("psycopg2").connect
        database_url = str(SETTINGS.database_url).replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )
        return connect(database_url)
