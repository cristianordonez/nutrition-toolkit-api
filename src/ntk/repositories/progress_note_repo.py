"""Persistence operations for resident progress notes."""

from __future__ import annotations

import typing

from sqlmodel import col, select

from ntk.models.sql.resident import ExtractionStatus, ResidentProgressNote

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ProgressNoteRepo:
    """Persist and retrieve resident progress notes."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, progress_note: ResidentProgressNote) -> ResidentProgressNote:
        """Persist a new progress note in the current transaction."""
        existing = self.get_by_key(progress_note.note_key)
        if existing is not None:
            return existing
        self.session.add(progress_note)
        self.session.flush()
        self.session.refresh(progress_note)
        return progress_note

    def get_by_key(self, note_key: str) -> ResidentProgressNote | None:
        """Return the progress note identified by ``note_key``, if present."""
        statement = select(ResidentProgressNote).where(
            ResidentProgressNote.note_key == note_key,
        )
        return self.session.exec(statement).first()

    def get_all(self) -> list[ResidentProgressNote]:
        """Return persisted progress notes in effective-date order."""
        statement = select(ResidentProgressNote).order_by(
            col(ResidentProgressNote.note_date),
            col(ResidentProgressNote.id),
        )
        return list(self.session.exec(statement).all())

    def update_identity(
        self,
        progress_note: ResidentProgressNote,
        *,
        resident_id: int,
        resident_facility_stay_id: int | None,
    ) -> ResidentProgressNote:
        """Correct the resident ownership of an existing progress note."""
        if (
            progress_note.resident_id == resident_id
            and progress_note.resident_facility_stay_id == resident_facility_stay_id
        ):
            return progress_note
        progress_note.resident_id = resident_id
        progress_note.resident_facility_stay_id = resident_facility_stay_id
        self.session.add(progress_note)
        self.session.flush()
        return progress_note

    def set_extraction_status(
        self,
        progress_note: ResidentProgressNote,
        status: ExtractionStatus,
    ) -> ResidentProgressNote:
        """Persist the extraction outcome for a previously stored note."""
        progress_note.extraction_status = status
        self.session.add(progress_note)
        self.session.commit()
        self.session.refresh(progress_note)
        return progress_note
