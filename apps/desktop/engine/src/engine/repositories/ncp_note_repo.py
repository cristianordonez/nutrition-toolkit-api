"""Persistence operations for Nutrition Care Process notes and examples."""

from __future__ import annotations

import typing

from sqlmodel import col, desc, select

from engine.models.clinical_facts import utc_now
from engine.models.ncp_note import NCPNoteStatus
from engine.models.sql.ncp_note import NCPNote

if typing.TYPE_CHECKING:
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


__all__ = ["NCPNoteRepo"]
