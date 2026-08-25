"""Search ingested clinical nutrition knowledge."""

from __future__ import annotations

import typing
from importlib import import_module

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.knowledge import KnowledgeType
from ntk.models.output import Output
from ntk.models.rag import RagSearchMatch
from ntk.models.settings import SETTINGS
from ntk.services.open_ai_service import OpenAIService

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from psycopg import Connection

_SEARCH_SQL = """
    SELECT k.id, k.filename, c.content,
           1 - (e.embedding_vector <=> %s::vector) AS similarity
    FROM knowledge_chunks_embeddings e
    JOIN knowledge_chunks c ON c.id = e.knowledge_chunk_id
    JOIN knowledge k ON k.id = c.knowledge_id
    WHERE k.knowledge_type IN (%s, %s)
    ORDER BY e.embedding_vector <=> %s::vector
    LIMIT %s
"""


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


class KnowledgeSearchController(BaseController):
    """Search diet and nutrition care manual embeddings."""

    name = "search"
    help = "Search clinical nutrition knowledge"
    options_model = KnowledgeSearchOptions

    def __init__(
        self,
        open_ai_service: OpenAIService | None = None,
        connection_factory: Callable[[], Connection[tuple[object, ...]]] | None = None,
    ) -> None:
        """Initialize optional search dependencies."""
        self.open_ai_service = open_ai_service
        self.connection_factory = connection_factory

    def search(self, text: str, top_k: int = 5) -> Output[KnowledgeSearchResponse]:
        """Normalize API search parameters and run the search workflow."""
        return self.run(
            KnowledgeSearchOptions(
                text=text,
                top_k=max(1, min(top_k, 20)),
            ),
        )

    def run(self, options: KnowledgeSearchOptions) -> Output[KnowledgeSearchResponse]:
        """Embed the query and return matching knowledge chunks."""
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
                    KnowledgeType.DIET_MANUAL.value,
                    KnowledgeType.NUTRITION_CARE_MANUAL.value,
                    vector,
                    options.top_k,
                ),
            )
            rows = cursor.fetchall()
        matches = [
            RagSearchMatch(
                document_id=typing.cast("UUID", row[0]),
                filename=str(row[1]),
                chunk_text=str(row[2]),
                similarity=float(str(row[3])),
            )
            for row in rows
        ]
        return Output(
            result=KnowledgeSearchResponse(matches=matches),
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
