"""Persistence operations for Nutrition Care Process notes and examples."""

from __future__ import annotations

import typing

from sqlalchemy import insert
from sqlalchemy import select as sql_select
from sqlmodel import col, desc, select

from engine.database.vectors import ncp_vectors, pack_embedding
from engine.models.clinical_facts import utc_now
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.rag import RagSearchMatch
from engine.models.sql.ncp_note import NCPNote
from engine.utils.misc import require_id

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel import Session


class NCPNoteRepo:
    """Store NCP notes independently from imported clinical sources."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an existing unit-of-work session."""
        self.session = session

    def get(self, note_id: int) -> NCPNote | None:
        """Return one note by primary key, if present."""
        return self.session.get(NCPNote, note_id)

    def save(self, note: NCPNote) -> NCPNote:
        """Persist a new or changed NCP note."""
        now = utc_now()
        if note.status is NCPNoteStatus.FINALIZED and note.finalized_at is None:
            note.finalized_at = now
        if note.status is not NCPNoteStatus.FINALIZED:
            note.finalized_at = None
        note.updated_at = now
        self.session.add(note)
        self.session.commit()
        self.session.refresh(note)
        return note

    def finalize(self, note_id: int) -> NCPNote | None:
        """Mark a stored draft as finalized and timestamp the transition."""
        note = self.get(note_id)
        if note is None:
            return None
        note.status = NCPNoteStatus.FINALIZED
        note.finalized_at = utc_now()
        return self.save(note)

    def latest_finalized(self, person_id: int) -> NCPNote | None:
        """Return a person's most recently finalized NCP note."""
        return self.session.exec(
            select(NCPNote)
            .where(NCPNote.person_id == person_id)
            .where(NCPNote.status == NCPNoteStatus.FINALIZED)
            .order_by(
                desc(col(NCPNote.finalized_at)),
                desc(col(NCPNote.created_at)),
                desc(col(NCPNote.id)),
            )
            .limit(1),
        ).first()

    def list_examples(self) -> list[NCPNote]:
        """Return all explicit style examples, newest first."""
        return list(
            self.session.exec(
                select(NCPNote)
                .where(NCPNote.status == NCPNoteStatus.EXAMPLE)
                .order_by(desc(col(NCPNote.created_at)), desc(col(NCPNote.id))),
            ).all(),
        )

    def list_for_person(self, person_id: int) -> list[NCPNote]:
        """Return all NCP notes for one person, newest first."""
        return list(
            self.session.exec(
                select(NCPNote)
                .where(NCPNote.person_id == person_id)
                .order_by(desc(col(NCPNote.created_at)), desc(col(NCPNote.id))),
            ).all(),
        )

    def existing_example_contents(self, contents: Sequence[str]) -> set[str]:
        """Return which of ``contents`` are already stored as examples."""
        if not contents:
            return set()
        return set(
            self.session.exec(
                select(NCPNote.content)
                .where(NCPNote.status == NCPNoteStatus.EXAMPLE)
                .where(col(NCPNote.content).in_(list(contents))),
            ).all(),
        )

    def add_examples(
        self,
        notes: Sequence[NCPNote],
        vectors: Sequence[list[float]],
        model: str,
    ) -> None:
        """Store style examples and their vectors in one transaction.

        Committed together so an example is never searchable-by-status yet
        missing from the vector table, or the reverse.
        """
        for note in notes:
            note.status = NCPNoteStatus.EXAMPLE
            note.finalized_at = None
        self.session.add_all(notes)
        self.session.flush()
        self.store_embeddings(notes, vectors, model)
        self.session.commit()

    def unembedded_examples(self, model: str, *, limit: int | None) -> list[NCPNote]:
        """Return examples not yet stored in the current model's vec0 table."""
        embedded = sql_select(ncp_vectors.c.ncp_note_id).where(
            ncp_vectors.c.model == model,
        )
        statement = (
            select(NCPNote)
            .where(NCPNote.status == NCPNoteStatus.EXAMPLE)
            .where(col(NCPNote.id).not_in(embedded))
            .order_by(col(NCPNote.id))
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

    def has_example_embeddings(self, model: str) -> bool:
        """Report whether retrieval can run before loading the embedding model."""
        statement = (
            select(ncp_vectors.c.ncp_note_id)
            .join(NCPNote, ncp_vectors.c.ncp_note_id == col(NCPNote.id))
            .where(ncp_vectors.c.model == model)
            .where(NCPNote.status == NCPNoteStatus.EXAMPLE)
            .limit(1)
        )
        return self.session.exec(statement).first() is not None

    def store_embeddings(
        self,
        notes: Sequence[NCPNote],
        vectors: Sequence[list[float]],
        model: str,
    ) -> None:
        """Replace each note's vector within the caller's transaction."""
        rows = [
            {
                "ncp_note_id": require_id(note.id),
                "model": model,
                "embedding": pack_embedding(vector),
            }
            for note, vector in zip(notes, vectors, strict=True)
        ]
        if not rows:
            return
        self.session.exec(
            ncp_vectors.delete().where(
                ncp_vectors.c.ncp_note_id.in_([row["ncp_note_id"] for row in rows]),
            ),
        )
        self.session.exec(insert(ncp_vectors), params=rows)

    def search_examples(
        self,
        query_vector: list[float],
        top_k: int,
        model: str,
        *,
        note_type: NCPNoteType | None = None,
    ) -> list[RagSearchMatch]:
        """Rank eligible examples inside vec0 before applying the result count."""
        if not any(query_vector):
            return []
        candidates = select(NCPNote.id).where(NCPNote.status == NCPNoteStatus.EXAMPLE)
        if note_type is not None:
            candidates = candidates.where(NCPNote.note_type == note_type)
        nearest = (
            sql_select(ncp_vectors.c.ncp_note_id, ncp_vectors.c.distance)
            .where(ncp_vectors.c.embedding.op("MATCH")(pack_embedding(query_vector)))
            .where(ncp_vectors.c.model == model)
            .where(ncp_vectors.c.ncp_note_id.in_(candidates))
            .where(ncp_vectors.c.k == top_k)
            .cte("nearest")
        )
        statement = (
            select(NCPNote, nearest.c.distance)
            .join(nearest, nearest.c.ncp_note_id == col(NCPNote.id))
            .order_by(nearest.c.distance)
        )
        return [
            RagSearchMatch(
                document_id=require_id(note.id),
                filename=note.note_type.value,
                chunk_text=note.content,
                similarity=1.0 - distance,
                section_title="NCP example",
            )
            for note, distance in self.session.exec(statement).all()
        ]


__all__ = ["NCPNoteRepo"]
