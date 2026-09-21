"""Persistence operations for Nutrition Care Process records and embeddings.

Unlike the pre-split ``ClinicalNoteRepo``, these records are keyed by an
opaque ``person_identifier`` string supplied by the desktop engine, not a
foreign key to a locally persisted ``Person`` row -- cloud-api does not
persist Person/clinical data (see the split refactor plan).
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessEmbedding,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
)
from ntk.utils.misc import require_id


class NCPRepo:
    """Persist Nutrition Care Process records, including their embeddings."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a shared database session."""
        self.session = session

    def get_ncp(
        self,
        ncp_id: int,
        person_identifier: str,
    ) -> NutritionCareProcess | None:
        """Return one Nutrition Care Process scoped to its owning person."""
        return self.session.exec(
            select(NutritionCareProcess).where(
                NutritionCareProcess.id == ncp_id,
                NutritionCareProcess.person_identifier == person_identifier,
            ),
        ).first()

    def list_ncps(self, person_identifier: str) -> list[NutritionCareProcess]:
        """Return all Nutrition Care Process records for one person."""
        return list(
            self.session.exec(
                select(NutritionCareProcess)
                .where(NutritionCareProcess.person_identifier == person_identifier)
                .order_by(
                    col(NutritionCareProcess.created_at).desc(),
                    col(NutritionCareProcess.id).desc(),
                ),
            ).all(),
        )

    def get_latest_ncp_for_person(
        self,
        person_identifier: str,
    ) -> NutritionCareProcess | None:
        """Return this person's own most recent finalized Nutrition Care Process."""
        return self.session.exec(
            select(NutritionCareProcess)
            .where(
                NutritionCareProcess.person_identifier == person_identifier,
                NutritionCareProcess.status == NutritionCareProcessStatus.FINALIZED,
            )
            .order_by(
                col(NutritionCareProcess.created_at).desc(),
                col(NutritionCareProcess.id).desc(),
            ),
        ).first()

    def get_embedding(
        self,
        ncp_id: int,
    ) -> NutritionCareProcessEmbedding | None:
        """Return the embedding associated with a Nutrition Care Process."""
        return self.session.exec(
            select(NutritionCareProcessEmbedding).where(
                NutritionCareProcessEmbedding.nutrition_care_process_id == ncp_id,
            ),
        ).first()

    def save_ncp(self, ncp: NutritionCareProcess) -> NutritionCareProcess:
        """Persist a Nutrition Care Process record."""
        try:
            self.session.add(ncp)
            self.session.commit()
            self.session.refresh(ncp)
        except Exception:
            self.session.rollback()
            raise
        return ncp

    def get_by_person_and_content_hash(
        self,
        person_identifier: str,
        content_hash: str,
    ) -> NutritionCareProcess | None:
        """Find a Nutrition Care Process by person and content hash."""
        return self.session.exec(
            select(NutritionCareProcess).where(
                NutritionCareProcess.person_identifier == person_identifier,
                NutritionCareProcess.content_hash == content_hash,
            ),
        ).first()

    def create_generated_draft(
        self,
        ncp: NutritionCareProcess,
    ) -> NutritionCareProcess:
        """Persist or retrieve an idempotent generated draft."""
        if (
            ncp.ncp_source is not NutritionCareProcessSource.GENERATED
            or ncp.status is not NutritionCareProcessStatus.DRAFT
        ):
            msg = "Only generated draft NCPs can use draft regeneration"
            raise ValueError(msg)
        existing = self.get_by_person_and_content_hash(
            ncp.person_identifier,
            ncp.content_hash,
        )
        if existing is not None:
            return existing
        try:
            return self.save_ncp(ncp)
        except IntegrityError:
            existing = self.get_by_person_and_content_hash(
                ncp.person_identifier,
                ncp.content_hash,
            )
            if existing is not None:
                return existing
            raise

    def update_ncp(
        self,
        ncp: NutritionCareProcess,
        *,
        embedding: list[float] | None = None,
        embedding_type: NutritionClinicalNoteType | None = None,
        model_name: str | None = None,
    ) -> NutritionCareProcess:
        """Persist Nutrition Care Process data and its optional embedding."""
        if embedding is not None and embedding_type is None:
            msg = "Nutrition clinical note type is required"
            raise ValueError(msg)
        try:
            self.session.add(ncp)
            if embedding is not None:
                required_embedding_type = typing.cast(
                    "NutritionClinicalNoteType",
                    embedding_type,
                )
                stored = self.get_embedding(require_id(ncp.id))
                if stored is None:
                    stored = NutritionCareProcessEmbedding(
                        nutrition_care_process_id=require_id(ncp.id),
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
            self.session.refresh(ncp)
        except Exception:
            self.session.rollback()
            raise
        return ncp

    def finalize_ncp(
        self,
        ncp_id: int,
        person_identifier: str,
    ) -> NutritionCareProcess | None:
        """Finalize a Nutrition Care Process record when it exists."""
        ncp = self.get_ncp(ncp_id, person_identifier)
        if ncp is None:
            return None
        if ncp.status is not NutritionCareProcessStatus.FINALIZED:
            ncp.status = NutritionCareProcessStatus.FINALIZED
            ncp.finalized_at = datetime.now(UTC)
            self.session.add(ncp)
            self.session.commit()
            self.session.refresh(ncp)
        return ncp

    def count_ncps(self, source_filename: str) -> int:
        """Count imported Nutrition Care Process records for a source file."""
        return len(
            self.session.exec(
                select(NutritionCareProcess.id).where(
                    NutritionCareProcess.ncp_source
                    == NutritionCareProcessSource.IMPORTED,
                    NutritionCareProcess.source_filename == source_filename,
                ),
            ).all(),
        )


__all__ = ["NCPRepo"]
