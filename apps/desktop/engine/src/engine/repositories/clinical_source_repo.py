"""Persistence operations for logical clinical source material."""

from __future__ import annotations

import typing

from sqlmodel import col, select

from engine.models.clinical_facts import utc_now
from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
)

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ClinicalSourceRepo:
    """Persist source material from which clinical facts are extracted."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an existing unit-of-work session."""
        self.session = session

    def get_by_id(self, source_id: int) -> ClinicalSource | None:
        """Return a source by primary key, if present."""
        return self.session.get(ClinicalSource, source_id)

    def get_by_key(self, source_key: str) -> ClinicalSource | None:
        """Return the source with the stable ingestion key, if present."""
        return self.session.exec(
            select(ClinicalSource).where(ClinicalSource.source_key == source_key),
        ).first()

    def create(self, source: ClinicalSource) -> ClinicalSource:
        """Create a source or return the source already using the same key."""
        existing = self.get_by_key(source.source_key)
        if existing is not None:
            return existing
        self.session.add(source)
        self.session.flush()
        self.session.refresh(source)
        return source

    def update_identity(
        self,
        source: ClinicalSource,
        *,
        person_id: int,
    ) -> ClinicalSource:
        """Associate an existing source with its resolved person."""
        if source.person_id != person_id:
            source.person_id = person_id
            source.updated_at = utc_now()
            self.session.add(source)
            self.session.flush()
        return source

    def set_extraction_status(
        self,
        source: ClinicalSource,
        status: ExtractionStatus,
    ) -> ClinicalSource:
        """Persist and commit a source's extraction status."""
        source.extraction_status = status
        source.updated_at = utc_now()
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def list_progress_notes(
        self,
        *,
        person_id: int | None = None,
        limit: int | None = None,
    ) -> list[ClinicalSource]:
        """List progress-note sources in reverse clinical order."""
        statement = select(ClinicalSource).where(
            ClinicalSource.source_kind == ClinicalSourceKind.PROGRESS_NOTE,
        )
        if person_id is not None:
            statement = statement.where(ClinicalSource.person_id == person_id)
        statement = statement.order_by(
            col(ClinicalSource.effective_at).desc().nulls_last(),
            col(ClinicalSource.id).desc(),
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())


__all__ = ["ClinicalSourceRepo"]
