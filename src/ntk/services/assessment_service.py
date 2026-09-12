"""Simple application operations for persisted nutrition assessments."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ntk.models.sql.person import PersonAssessment
    from ntk.repositories.assessment_repo import AssessmentRepo


class AssessmentService:
    """Expose simple assessment reads above the repository boundary."""

    def __init__(self, repository: AssessmentRepo) -> None:
        """Store the assessment repository."""
        self.repository = repository

    def get(self, assessment_id: int) -> PersonAssessment | None:
        """Return one assessment by its database identifier."""
        return self.repository.get_by_id(assessment_id)

    def list_assessments(self) -> list[PersonAssessment]:
        """Return all assessments newest first."""
        return self.repository.get_all()


__all__ = ["AssessmentService"]
