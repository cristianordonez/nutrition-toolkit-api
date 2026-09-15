"""Persistence operations for locally stored clinical notes."""

from __future__ import annotations

from sqlmodel import Session, col, select

from engine.models.sql import ExtractionStatus, PersonClinicalNote


class ClinicalNoteRepo:
    """Persist clinical notes ingested from local documents."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a shared database session."""
        self.session = session

    def create(self, note: PersonClinicalNote) -> PersonClinicalNote:
        """Persist an ingested clinical note in the current transaction."""
        existing = self.get_by_key(note.note_key)
        if existing is not None:
            return existing
        self.session.add(note)
        self.session.flush()
        self.session.refresh(note)
        return note

    def get_by_key(self, note_key: str) -> PersonClinicalNote | None:
        """Return a clinical note by its source-stable key."""
        return self.session.exec(
            select(PersonClinicalNote).where(PersonClinicalNote.note_key == note_key),
        ).first()

    def list_clinical_notes(self) -> list[PersonClinicalNote]:
        """Return all clinical notes in deterministic chronological order."""
        return list(
            self.session.exec(
                select(PersonClinicalNote).order_by(
                    col(PersonClinicalNote.note_date),
                    col(PersonClinicalNote.id),
                ),
            ).all(),
        )

    def update_identity(
        self,
        note: PersonClinicalNote,
        *,
        person_id: int,
    ) -> PersonClinicalNote:
        """Associate a clinical note with a person when the identity changes."""
        if note.person_id != person_id:
            note.person_id = person_id
            self.session.add(note)
            self.session.flush()
        return note

    def set_extraction_status(
        self,
        note: PersonClinicalNote,
        status: ExtractionStatus,
    ) -> PersonClinicalNote:
        """Persist the extraction status for a clinical note."""
        note.extraction_status = status
        self.session.add(note)
        self.session.commit()
        self.session.refresh(note)
        return note


__all__ = ["ClinicalNoteRepo"]
