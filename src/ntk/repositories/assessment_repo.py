"""Persistence operations for nutrition assessments and their embeddings."""

from __future__ import annotations

import logging
import typing
from datetime import UTC, datetime

from sqlmodel import Session, col, delete, select

from ntk.models.sql.resident import (
    AssessmentSource,
    ResidentAssessment,
    ResidentAssessmentEmbedding,
    StatusType,
)
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class AssessmentRepo:
    """Store complete assessments independently from clinical knowledge."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def get_by_id(self, assessment_id: int) -> ResidentAssessment | None:
        """Return one resident assessment by its database identifier."""
        return self.session.get(ResidentAssessment, assessment_id)

    def get_by_source_progress_note_id(
        self,
        progress_note_id: int,
    ) -> ResidentAssessment | None:
        """Return the assessment synchronized from one progress note."""
        statement = select(ResidentAssessment).where(
            ResidentAssessment.source_progress_note_id == progress_note_id,
        )
        return self.session.exec(statement).first()

    def get_embedding(
        self,
        assessment_id: int,
    ) -> ResidentAssessmentEmbedding | None:
        """Return the stored vector record for one assessment."""
        statement = select(ResidentAssessmentEmbedding).where(
            ResidentAssessmentEmbedding.resident_assessment_id == assessment_id,
        )
        return self.session.exec(statement).first()

    def create(self, assessment: ResidentAssessment) -> ResidentAssessment:
        """Persist an assessment before its repairable embedding step."""
        try:
            self.session.add(assessment)
            self.session.commit()
            self.session.refresh(assessment)
        except Exception:
            self.session.rollback()
            raise
        return assessment

    def get_all(self) -> list[ResidentAssessment]:
        """Return all assessments newest first."""
        return list(
            self.session.exec(
                select(ResidentAssessment).order_by(
                    col(ResidentAssessment.created_at).desc(),
                ),
            ).all(),
        )

    def update(
        self,
        assessment: ResidentAssessment,
        *,
        embedding: list[float] | None = None,
        model_name: str | None = None,
    ) -> ResidentAssessment:
        """Persist assessment edits and optionally replace its embedding."""
        try:
            self.session.add(assessment)
            if embedding is not None:
                stored_embedding = self.get_embedding(require_id(assessment.id))
                if stored_embedding is None:
                    stored_embedding = ResidentAssessmentEmbedding(
                        resident_assessment_id=require_id(assessment.id),
                        embedding_vector=embedding,
                        model_name=model_name or "",
                    )
                else:
                    stored_embedding.embedding_vector = embedding
                    stored_embedding.model_name = (
                        model_name or stored_embedding.model_name
                    )
                self.session.add(stored_embedding)
            self.session.commit()
            self.session.refresh(assessment)
        except Exception:
            self.session.rollback()
            raise
        return assessment

    def finalize(self, assessment_id: int) -> ResidentAssessment | None:
        """Mark one resident assessment as finalized and return it."""
        assessment = self.get_by_id(assessment_id)
        if assessment is None:
            return None
        if assessment.status is not StatusType.FINALIZED:
            assessment.status = StatusType.FINALIZED
            assessment.finalized_at = datetime.now(UTC)
            self.session.add(assessment)
            self.session.commit()
            self.session.refresh(assessment)
        return assessment

    def ingest_one(
        self,
        assessment: ResidentAssessment,
        embeddings: list[float],
        model_name: str | None,
    ) -> ResidentAssessment | None:
        """Ingest single assessment."""
        assessments = self.ingest_many(
            [assessment],
            [embeddings],
            model_name,
        )
        return assessments[0] if assessments else None

    def ingest_many(
        self,
        assessments: list[ResidentAssessment],
        embeddings: list[list[float]],
        model_name: str | None,
    ) -> list[ResidentAssessment]:
        """Store extracted SQL assessment records and their embeddings."""
        self._validate(assessments, embeddings, model_name)
        candidates = list(zip(assessments, embeddings, strict=True))
        try:
            self.session.add_all(assessments)
            self.session.flush()
            self.session.add_all(
                [
                    ResidentAssessmentEmbedding(
                        resident_assessment_id=require_id(assessment.id),
                        embedding_vector=embedding,
                        model_name=model_name or "",
                    )
                    for assessment, embedding in candidates
                ],
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return assessments

    def ingest(
        self,
        assessments: list[ResidentAssessment],
        embeddings: list[list[float]],
        model_name: str | None,
        *,
        overwrite: bool = False,
    ) -> list[ResidentAssessment]:
        """Store nonduplicate assessments, optionally replacing imported files."""
        self._validate(assessments, embeddings, model_name)
        if overwrite:
            filenames = {
                assessment.source_filename
                for assessment in assessments
                if assessment.source_filename is not None
            }
            self._delete_imported_sources(filenames)

        unique_assessments: list[ResidentAssessment] = []
        unique_embeddings: list[list[float]] = []
        seen_hashes: set[str] = set()
        for assessment, embedding in zip(assessments, embeddings, strict=True):
            if assessment.content_hash in seen_hashes:
                continue
            seen_hashes.add(assessment.content_hash)
            if self.is_duplicate_assessment(assessment):
                continue
            unique_assessments.append(assessment)
            unique_embeddings.append(embedding)
        return self.ingest_many(
            unique_assessments,
            unique_embeddings,
            model_name,
        )

    def _delete_imported_sources(self, filenames: set[str]) -> None:
        if not filenames:
            return
        assessment_ids = self.session.exec(
            select(ResidentAssessment.id).where(
                ResidentAssessment.assessment_source == AssessmentSource.IMPORTED,
                col(ResidentAssessment.source_filename).in_(filenames),
            ),
        ).all()
        if assessment_ids:
            self.session.exec(
                delete(ResidentAssessmentEmbedding).where(
                    col(ResidentAssessmentEmbedding.resident_assessment_id).in_(
                        assessment_ids,
                    ),
                ),
            )
            self.session.exec(
                delete(ResidentAssessment).where(
                    col(ResidentAssessment.id).in_(assessment_ids),
                ),
            )
            self.session.flush()

    def is_duplicate_assessment(self, assessment: ResidentAssessment) -> bool:
        """Use content hash to check if assessment exists in database.

        :param assessment: Assessment model instance
        :return: True if content hash exists
        """
        result = set(
            self.session.exec(
                select(ResidentAssessment.id).where(
                    ResidentAssessment.resident_id == assessment.resident_id,
                    ResidentAssessment.content_hash == assessment.content_hash,
                ),
            ).all(),
        )
        return len(result) > 0

    def count_assessments(self, source_filename: str) -> int:
        """Return the number of assessments extracted from one imported file."""
        return len(
            self.session.exec(
                select(ResidentAssessment.id).where(
                    ResidentAssessment.assessment_source == AssessmentSource.IMPORTED,
                    ResidentAssessment.source_filename == source_filename,
                ),
            ).all(),
        )

    @staticmethod
    def _validate(
        assessments: Sequence[ResidentAssessment],
        embeddings: Sequence[list[float]],
        model_name: str | None,
    ) -> None:
        if len(assessments) != len(embeddings):
            msg = "Each assessment must have one embedding"
            raise ValueError(msg)
        if assessments and not model_name:
            msg = "Embedding model name is required"
            raise ValueError(msg)
