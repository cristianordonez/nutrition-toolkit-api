"""Synchronize historical assessments from persisted progress notes."""

from __future__ import annotations

import logging
import typing
from hashlib import sha256

from pydantic import BaseModel, PrivateAttr

from ntk.models.sql.resident import (
    AssessmentSource,
    ResidentAssessment,
    ResidentProgressNote,
    StatusType,
)
from ntk.services.assessment.embedding_service import AssessmentEmbeddingService
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from ntk.repositories.assessment_repo import AssessmentRepo
    from ntk.repositories.progress_note_repo import ProgressNoteRepo

_NUTRITION_ASSESSMENT_TYPE_TERMS = (
    "dietary",
    "dietitian",
    "dietician",
    "dietitician",
    "nutrition",
)
logger = logging.getLogger(__name__)


class AssessmentSyncResult(BaseModel):
    """Summary of one historical-assessment synchronization run."""

    scanned: int = 0
    assessments_created: int = 0
    assessments_existing: int = 0
    embeddings_created: int = 0
    embeddings_existing: int = 0
    skipped_not_nutrition: int = 0
    failed: int = 0
    _created_assessments: list[ResidentAssessment] = PrivateAttr(default_factory=list)

    @property
    def created_assessments(self) -> list[ResidentAssessment]:
        """Return assessments created during this run for internal callers."""
        return self._created_assessments


class AssessmentSyncService:
    """Create historical assessments from eligible persisted progress notes."""

    def __init__(
        self,
        progress_note_repository: ProgressNoteRepo,
        assessment_repository: AssessmentRepo,
        embedding_service: AssessmentEmbeddingService | None = None,
    ) -> None:
        """Service for syncing progress notes to nutrition assessment."""
        self.progress_note_repository = progress_note_repository
        self.assessment_repository = assessment_repository
        self.embedding_service = embedding_service or AssessmentEmbeddingService(
            assessment_repository,
        )

    async def sync_assessments(self) -> AssessmentSyncResult:
        """Create or repair historical assessments and their embeddings."""
        result = AssessmentSyncResult()
        for note in self.progress_note_repository.get_all():
            result.scanned += 1
            if not self.is_assessment_note(note):
                result.skipped_not_nutrition += 1
                continue
            try:
                assessment = self.assessment_repository.get_by_source_progress_note_id(
                    require_id(note.id),
                )
                if assessment is None:
                    assessment = self.assessment_repository.create(
                        self._build_assessment(note),
                    )
                    result.assessments_created += 1
                    result.created_assessments.append(assessment)
                else:
                    result.assessments_existing += 1
                if assessment.status is not StatusType.FINALIZED:
                    continue
                if await self.embedding_service.embed_assessment(assessment):
                    result.embeddings_created += 1
                else:
                    result.embeddings_existing += 1
            except Exception:
                result.failed += 1
                logger.exception("Failed to synchronize progress note %s", note.id)
        return result

    async def sync(self) -> AssessmentSyncResult:
        """Backward-compatible alias for the async synchronization workflow."""
        return await self.sync_assessments()

    @staticmethod
    def is_assessment_note(note: ResidentProgressNote) -> bool:
        """Return whether the existing note type denotes nutrition documentation."""
        note_type = " ".join((note.note_type or "").casefold().split())
        return any(term in note_type for term in _NUTRITION_ASSESSMENT_TYPE_TERMS)

    @staticmethod
    def _build_assessment(note: ResidentProgressNote) -> ResidentAssessment:
        content = note.note_text
        if not content.strip():
            msg = f"Progress note {note.id} has no assessment text"
            raise ValueError(msg)
        creator = (note.author or "").strip() or "unknown"
        normalized_content = " ".join(content.split())
        return ResidentAssessment(
            resident_id=note.resident_id,
            resident_facility_stay_id=note.resident_facility_stay_id,
            source_progress_note_id=require_id(note.id),
            content=content,
            assessment_source=AssessmentSource.IMPORTED,
            content_hash=sha256(normalized_content.encode()).hexdigest(),
            assessment_date=note.note_date.date(),
            created_by=creator,
            status=StatusType.FINALIZED,
            finalized_at=note.note_date,
        )


__all__ = ["AssessmentSyncResult", "AssessmentSyncService"]
