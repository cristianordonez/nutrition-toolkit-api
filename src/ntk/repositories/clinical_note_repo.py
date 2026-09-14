"""Persistence operations for clinical notes and nutrition-note embeddings."""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from ntk.models.sql.person import (
    ExtractionStatus,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
    PersonClinicalNote,
    PersonNutritionClinicalNoteEmbedding,
)
from ntk.utils.misc import require_id


class ClinicalNoteRepo:
    """Persist clinical notes, including their Nutrition Care Process subtype."""

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

    def get_ncp(self, note_id: int) -> PersonClinicalNote | None:
        """Return a clinical note populated with Nutrition Care Process data."""
        return self.session.exec(
            select(PersonClinicalNote).where(
                PersonClinicalNote.id == note_id,
                col(PersonClinicalNote.ncp_source).is_not(None),
            ),
        ).first()

    def list_ncps(self) -> list[PersonClinicalNote]:
        """Return clinical notes containing Nutrition Care Process data."""
        return list(
            self.session.exec(
                select(PersonClinicalNote)
                .where(col(PersonClinicalNote.ncp_source).is_not(None))
                .order_by(
                    col(PersonClinicalNote.note_date).desc(),
                    col(PersonClinicalNote.created_at).desc(),
                    col(PersonClinicalNote.id).desc(),
                ),
            ).all(),
        )

    def get_embedding(
        self,
        note_id: int,
    ) -> PersonNutritionClinicalNoteEmbedding | None:
        """Return the nutrition embedding associated with a clinical note."""
        return self.session.exec(
            select(PersonNutritionClinicalNoteEmbedding).where(
                PersonNutritionClinicalNoteEmbedding.person_clinical_note_id == note_id,
            ),
        ).first()

    def save_ncp(self, note: PersonClinicalNote) -> PersonClinicalNote:
        """Persist Nutrition Care Process fields on a clinical note."""
        try:
            self.session.add(note)
            self.session.commit()
            self.session.refresh(note)
        except Exception:
            self.session.rollback()
            raise
        return note

    def get_by_person_and_content_hash(
        self,
        person_id: int,
        content_hash: str,
    ) -> PersonClinicalNote | None:
        """Find Nutrition Care Process data by person and content hash."""
        return self.session.exec(
            select(PersonClinicalNote).where(
                PersonClinicalNote.person_id == person_id,
                PersonClinicalNote.content_hash == content_hash,
                col(PersonClinicalNote.ncp_source).is_not(None),
            ),
        ).first()

    def create_generated_draft(
        self,
        note: PersonClinicalNote,
    ) -> PersonClinicalNote:
        """Persist or retrieve an idempotent generated draft."""
        if (
            note.ncp_source is not NutritionCareProcessSource.GENERATED
            or note.status is not NutritionCareProcessStatus.DRAFT
            or note.content_hash is None
        ):
            msg = "Only generated draft NCPs can use draft regeneration"
            raise ValueError(msg)
        existing = self.get_by_person_and_content_hash(
            note.person_id,
            note.content_hash,
        )
        if existing is not None:
            return existing
        try:
            return self.save_ncp(note)
        except IntegrityError:
            existing = self.get_by_person_and_content_hash(
                note.person_id,
                note.content_hash,
            )
            if existing is not None:
                return existing
            raise

    def update_ncp(
        self,
        note: PersonClinicalNote,
        *,
        embedding: list[float] | None = None,
        embedding_type: NutritionClinicalNoteType | None = None,
        model_name: str | None = None,
    ) -> PersonClinicalNote:
        """Persist Nutrition Care Process data and its optional embedding."""
        if embedding is not None and embedding_type is None:
            msg = "Nutrition clinical note type is required"
            raise ValueError(msg)
        try:
            self.session.add(note)
            if embedding is not None:
                required_embedding_type = typing.cast(
                    "NutritionClinicalNoteType",
                    embedding_type,
                )
                stored = self.get_embedding(require_id(note.id))
                if stored is None:
                    stored = PersonNutritionClinicalNoteEmbedding(
                        person_clinical_note_id=require_id(note.id),
                        embedding_vector=embedding,
                        type=required_embedding_type,
                        model_name=model_name or "",
                    )
                else:
                    stored.embedding_vector = embedding
                    stored.type = required_embedding_type
                    stored.model_name = model_name or stored.model_name
                self.session.add(stored)
            self.session.commit()
            self.session.refresh(note)
        except Exception:
            self.session.rollback()
            raise
        return note

    def finalize_ncp(self, note_id: int) -> PersonClinicalNote | None:
        """Finalize Nutrition Care Process data when it exists."""
        note = self.get_ncp(note_id)
        if note is None:
            return None
        if note.status is not NutritionCareProcessStatus.FINALIZED:
            note.status = NutritionCareProcessStatus.FINALIZED
            note.finalized_at = datetime.now(UTC)
            self.session.add(note)
            self.session.commit()
            self.session.refresh(note)
        return note

    def count_ncps(self, source_filename: str) -> int:
        """Count imported Nutrition Care Process records for a source file."""
        return len(
            self.session.exec(
                select(PersonClinicalNote.id).where(
                    PersonClinicalNote.ncp_source
                    == NutritionCareProcessSource.IMPORTED,
                    PersonClinicalNote.source_filename == source_filename,
                ),
            ).all(),
        )


__all__ = ["ClinicalNoteRepo"]
