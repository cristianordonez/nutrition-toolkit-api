"""Update persisted resident assessments."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime
from hashlib import sha256

from ntk.models.sql.resident import ResidentAssessment, StatusType
from ntk.services.embedding_service import EmbeddingService

if typing.TYPE_CHECKING:
    from ntk.repositories.assessment_repo import AssessmentRepo


class AssessmentUpdateService:
    """Apply assessment edits and keep its vector synchronized."""

    def __init__(self, assessment_repository: AssessmentRepo) -> None:
        """Store the assessment repository."""
        self.assessment_repository = assessment_repository

    async def update(
        self,
        assessment_id: int,
        *,
        content: str | None = None,
        assessment_date: date | None = None,
        created_by: str | None = None,
        status: StatusType | None = None,
    ) -> ResidentAssessment | None:
        """Apply supplied fields and return the updated assessment."""
        assessment = self.assessment_repository.get_by_id(assessment_id)
        if assessment is None:
            return None
        content_changed = content is not None
        if content is not None:
            normalized_content = " ".join(content.split())
            if not normalized_content:
                message = "Assessment content cannot be empty"
                raise ValueError(message)
            assessment.content = content.strip()
            assessment.content_hash = sha256(normalized_content.encode()).hexdigest()
        if assessment_date is not None:
            assessment.assessment_date = assessment_date
        if created_by is not None:
            normalized_creator = created_by.strip()
            if not normalized_creator:
                message = "Assessment creator cannot be empty"
                raise ValueError(message)
            assessment.created_by = normalized_creator
        if status is not None:
            assessment.status = status
            if status is StatusType.FINALIZED and assessment.finalized_at is None:
                assessment.finalized_at = datetime.now(UTC)
            elif status is StatusType.DRAFT:
                assessment.finalized_at = None
        embedding, embedding_model = await self._updated_embedding(
            assessment,
            content_changed=content_changed,
        )
        return self.assessment_repository.update(
            assessment,
            embedding=embedding,
            model_name=embedding_model,
        )

    @staticmethod
    async def _updated_embedding(
        assessment: ResidentAssessment,
        *,
        content_changed: bool,
    ) -> tuple[list[float] | None, str | None]:
        """Embed edited content only when the assessment is finalized."""
        if not content_changed or assessment.status is not StatusType.FINALIZED:
            return None, None
        embedding_service = EmbeddingService()
        embedding = await embedding_service.get_embedding_async(assessment.content)
        return embedding, embedding_service.embedding_model


__all__ = ["AssessmentUpdateService"]
