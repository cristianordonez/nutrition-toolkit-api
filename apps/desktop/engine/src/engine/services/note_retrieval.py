"""Supply the note agent with prior notes: the resident's own, and examples.

The prompt asks for two distinct things and treats them very differently:

``previous_ncp`` is this resident's own most recent finalized NCP note. It is
deterministic -- no embeddings -- and continuity is measured against it.

``relevant_ncps`` are explicit ``example`` NCP notes retrieved by similarity.
Bundled examples are global rows with no person or facility association; raw
progress-note clinical sources are never embedded or used as style examples.
"""

from __future__ import annotations

import logging
import typing

from engine.models.ncp_context import PreviousNCPNote, RetrievedNote
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.services.embedding_service import (
    EmbeddingService,
    EmbeddingUnavailableError,
)

if typing.TYPE_CHECKING:
    from sqlmodel import Session

logger = logging.getLogger(__name__)

#: How many style examples to retrieve. Enough to show a house style, few
#: enough that they cannot crowd out the resident's own record.
DEFAULT_TOP_K = 3


class NoteRetrievalService:
    """Assemble the prior-note context for one generation request."""

    def __init__(
        self,
        session: Session,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        """Initialize with a facts-database session."""
        self.session = session
        self.notes = NCPNoteRepo(session)
        self.embeddings = embeddings or EmbeddingService(session)

    def previous_note(self, person_id: int) -> PreviousNCPNote | None:
        """Return this person's most recently finalized NCP note, if any."""
        note = self.notes.latest_finalized(person_id)
        if note is None or note.finalized_at is None:
            return None
        return PreviousNCPNote(
            note_date=note.finalized_at.date(),
            note_text=note.content,
        )

    async def style_examples(
        self,
        query_text: str,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[RetrievedNote]:
        """Return similar explicit example notes, for style only.

        Retrieval is best-effort. A device with no embedding backend
        configured still generates notes -- without examples, which the
        prompt already handles as the absent case -- rather than failing the
        whole request over a style aid.
        """
        try:
            await self.embeddings.index_examples()
            matches = await self.embeddings.search_examples_async(
                query_text,
                top_k=top_k,
            )
        except EmbeddingUnavailableError:
            logger.warning(
                "Generating without style examples: no embedding backend",
                exc_info=True,
            )
            return []
        return [
            RetrievedNote(note_text=match.chunk_text)
            for match in matches
            if match.chunk_text
        ]


__all__ = ["DEFAULT_TOP_K", "NoteRetrievalService"]
