"""Persistence operations for person progress notes."""

from __future__ import annotations

import typing

from sqlmodel import col, select

from ntk.models.sql.person import ExtractionStatus, PersonProgressNote

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ProgressNoteRepo:
    """Persist and retrieve person progress notes."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, progress_note: PersonProgressNote) -> PersonProgressNote:
        """Persist a new progress note in the current transaction."""
        existing = self.get_by_key(progress_note.note_key)
        if existing is not None:
            return existing
        self.session.add(progress_note)
        self.session.flush()
        self.session.refresh(progress_note)
        return progress_note

    def get_by_key(self, note_key: str) -> PersonProgressNote | None:
        """Return the progress note identified by ``note_key``, if present."""
        statement = select(PersonProgressNote).where(
            PersonProgressNote.note_key == note_key,
        )
        return self.session.exec(statement).first()

    def get_all(self) -> list[PersonProgressNote]:
        """Return persisted progress notes in effective-date order."""
        statement = select(PersonProgressNote).order_by(
            col(PersonProgressNote.note_date),
            col(PersonProgressNote.id),
        )
        return list(self.session.exec(statement).all())

    def update_identity(
        self,
        progress_note: PersonProgressNote,
        *,
        person_id: int,
    ) -> PersonProgressNote:
        """Correct the person ownership of an existing progress note."""
        if progress_note.person_id == person_id:
            return progress_note
        progress_note.person_id = person_id
        self.session.add(progress_note)
        self.session.flush()
        return progress_note

    def set_extraction_status(
        self,
        progress_note: PersonProgressNote,
        status: ExtractionStatus,
    ) -> PersonProgressNote:
        """Persist the extraction outcome for a previously stored note."""
        progress_note.extraction_status = status
        self.session.add(progress_note)
        self.session.commit()
        self.session.refresh(progress_note)
        return progress_note
