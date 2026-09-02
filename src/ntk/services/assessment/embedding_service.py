"""Create and persist assessment embeddings through the shared vector model."""

from __future__ import annotations

import typing

from ntk.models.sql.resident import StatusType
from ntk.services.embedding_service import EmbeddingService
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from ntk.models.sql.resident import ResidentAssessment
    from ntk.repositories.assessment_repo import AssessmentRepo


class AssessmentEmbeddingService:
    """Ensure each persisted assessment has one text embedding."""

    def __init__(
        self,
        assessment_repository: AssessmentRepo,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Store persistence and vector-generation dependencies."""
        self.assessment_repository = assessment_repository
        self.embedding_service = embedding_service or EmbeddingService()

    async def embed_assessment(self, assessment: ResidentAssessment) -> bool:
        """Create a missing assessment embedding and report whether one was added."""
        if assessment.status is not StatusType.FINALIZED:
            return False
        assessment_id = require_id(assessment.id)
        if self.assessment_repository.get_embedding(assessment_id) is not None:
            return False
        embedding = await self.embedding_service.get_embedding_async(
            assessment.content,
        )
        self.assessment_repository.update(
            assessment,
            embedding=embedding,
            model_name=self.embedding_service.embedding_model,
        )
        return True


__all__ = ["AssessmentEmbeddingService"]
