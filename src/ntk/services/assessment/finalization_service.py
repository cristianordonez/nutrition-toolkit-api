"""Finalize persisted resident assessments."""

from __future__ import annotations

import typing

from ntk.models.sql.resident import ResidentAssessment  # noqa: TC001
from ntk.services.assessment.embedding_service import AssessmentEmbeddingService

if typing.TYPE_CHECKING:
    from ntk.repositories.assessment_repo import AssessmentRepo


class AssessmentFinalizationService:
    """Finalize an assessment and ensure its retrieval embedding exists."""

    def __init__(
        self,
        assessment_repository: AssessmentRepo,
        embedding_service: AssessmentEmbeddingService | None = None,
    ) -> None:
        """Store finalization and embedding dependencies."""
        self.assessment_repository = assessment_repository
        self.embedding_service = embedding_service or AssessmentEmbeddingService(
            assessment_repository,
        )

    async def finalize(self, assessment_id: int) -> ResidentAssessment | None:
        """Finalize and embed an assessment when it exists."""
        assessment = self.assessment_repository.finalize(assessment_id)
        if assessment is not None:
            await self.embedding_service.embed_assessment(assessment)
        return assessment


__all__ = ["AssessmentFinalizationService"]
