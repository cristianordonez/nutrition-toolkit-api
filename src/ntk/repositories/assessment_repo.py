"""Persistence operations for nutrition assessments and their embeddings."""

from __future__ import annotations

import logging
import typing

from sqlmodel import Session, col, delete, select

from ntk.models.sql.assessment import (
    Assessment,
    AssessmentEmbedding,
    AssessmentSource,
)

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class AssessmentRepo:
    """Store complete assessments independently from clinical knowledge."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def ingest_one(
        self,
        assessment: Assessment,
        embeddings: list[float],
        model_name: str | None,
    ) -> Assessment | None:
        """Ingest single assessment."""
        assessments = self.ingest_many(
            [assessment],
            [embeddings],
            model_name,
        )
        return assessments[0] if assessments else None

    def ingest_many(
        self,
        assessments: list[Assessment],
        embeddings: list[list[float]],
        model_name: str | None,
    ) -> list[Assessment]:
        """Store extracted SQL assessment records and their embeddings."""
        self._validate(assessments, embeddings, model_name)
        candidates = list(zip(assessments, embeddings, strict=True))
        self.session.add_all(assessments)
        self.session.flush()
        self.session.add_all(
            [
                AssessmentEmbedding(
                    assessment_id=assessment.id,
                    embedding_vector=embedding,
                    model_name=model_name or "",
                )
                for assessment, embedding in candidates
            ],
        )
        self.session.commit()
        return assessments

    def ingest(
        self,
        assessments: list[Assessment],
        embeddings: list[list[float]],
        model_name: str | None,
        *,
        overwrite: bool = False,
    ) -> list[Assessment]:
        """Store nonduplicate assessments, optionally replacing uploaded files."""
        self._validate(assessments, embeddings, model_name)
        if overwrite:
            filenames = {
                assessment.source_filename
                for assessment in assessments
                if assessment.source_filename is not None
            }
            self._delete_uploaded_sources(filenames)

        unique_assessments: list[Assessment] = []
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

    def _delete_uploaded_sources(self, filenames: set[str]) -> None:
        if not filenames:
            return
        assessment_ids = self.session.exec(
            select(Assessment.id).where(
                Assessment.source == AssessmentSource.UPLOADED,
                col(Assessment.source_filename).in_(filenames),
            ),
        ).all()
        if assessment_ids:
            self.session.exec(
                delete(AssessmentEmbedding).where(
                    col(AssessmentEmbedding.assessment_id).in_(assessment_ids),
                ),
            )
            self.session.exec(
                delete(Assessment).where(col(Assessment.id).in_(assessment_ids)),
            )
            self.session.flush()

    def is_duplicate_assessment(self, assessment: Assessment) -> bool:
        """Use content hash to check if assessment exists in database.

        :param assessment: Assessment model instance
        :return: True if content hash exists
        """
        result = set(
            self.session.exec(
                select(Assessment.id).where(
                    Assessment.content_hash == assessment.content_hash,
                ),
            ).all(),
        )
        return len(result) > 0

    def count_assessments(self, source_filename: str) -> int:
        """Return the number of assessments extracted from one uploaded file."""
        return len(
            self.session.exec(
                select(Assessment.id).where(
                    Assessment.source == AssessmentSource.UPLOADED,
                    Assessment.source_filename == source_filename,
                ),
            ).all(),
        )

    @staticmethod
    def _validate(
        assessments: Sequence[Assessment],
        embeddings: Sequence[list[float]],
        model_name: str | None,
    ) -> None:
        if len(assessments) != len(embeddings):
            msg = "Each assessment must have one embedding"
            raise ValueError(msg)
        if assessments and not model_name:
            msg = "Embedding model name is required"
            raise ValueError(msg)
