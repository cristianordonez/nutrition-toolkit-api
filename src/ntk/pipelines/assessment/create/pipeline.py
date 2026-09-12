"""Multistep workflows for generating and maintaining person assessments."""

from __future__ import annotations

import asyncio
import logging
import typing
from datetime import UTC, date, datetime
from hashlib import sha256

from pydantic import BaseModel, PrivateAttr

from ntk.agents.assessment_agent import ASSESSMENT_MODEL, AssessmentAgent
from ntk.models.sql.person import (
    AssessmentSource,
    Person,
    PersonAssessment,
    PersonProgressNote,
    StatusType,
)
from ntk.pipelines.assessment.create.context_budgeter import (
    ContextBudgeter,
    ContextBudgetResult,
)
from ntk.services.embedding_service import EmbeddingService
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from ntk.models.person_detail import PersonDetail
    from ntk.repositories.assessment_repo import AssessmentRepo
    from ntk.repositories.embedding_repo import EmbeddingRepo
    from ntk.repositories.food_repo import FoodRepo
    from ntk.repositories.progress_note_repo import ProgressNoteRepo
    from ntk.services.person.person_service import PersonService


_NUTRITION_ASSESSMENT_TYPE_TERMS = (
    "dietary",
    "dietitian",
    "dietician",
    "dietitician",
    "nutrition",
)
_ASSESSMENT_MATCH_LIMIT = 5
logger = logging.getLogger(__name__)


class AssessmentGenerationRequest(typing.Protocol):
    """Person-specific input accepted by batch assessment generation."""

    source_person_identifier: str
    source_system: str
    facility_identifier: str | None
    context: str | None


class AssessmentSyncResult(BaseModel):
    """Summary of one historical-assessment synchronization run."""

    scanned: int = 0
    assessments_created: int = 0
    assessments_existing: int = 0
    embeddings_created: int = 0
    embeddings_existing: int = 0
    skipped_not_nutrition: int = 0
    failed: int = 0
    _created_assessments: list[PersonAssessment] = PrivateAttr(default_factory=list)

    @property
    def created_assessments(self) -> list[PersonAssessment]:
        """Return assessments created during this run for internal callers."""
        return self._created_assessments


class AssessmentPipeline:
    """Coordinate assessment workflows through shared repository dependencies."""

    def __init__(  # noqa: PLR0913
        self,
        assessment_repository: AssessmentRepo,
        *,
        person_service: PersonService | None = None,
        embedding_repository: EmbeddingRepo | None = None,
        food_repository: FoodRepo | None = None,
        progress_note_repository: ProgressNoteRepo | None = None,
        embedding_service: EmbeddingService | None = None,
        context_budgeter: ContextBudgeter | None = None,
    ) -> None:
        """Store workflow dependencies and lazily create vector infrastructure."""
        self.assessment_repository = assessment_repository
        self.person_service = person_service
        self.embedding_repository = embedding_repository
        self.food_repository = food_repository
        self.progress_note_repository = progress_note_repository
        self.embedding_service = embedding_service
        self.context_budgeter = context_budgeter or ContextBudgeter()

    async def generate(
        self,
        source_person_identifier: str,
        *,
        facility_identifier: str | None = None,
        context: str | None = None,
    ) -> PersonAssessment:
        """Resolve a person, retrieve context, and persist a draft assessment."""
        person_detail = self._person_service().get_person_detail(
            source_person_identifier,
            facility_identifier=facility_identifier,
        )
        person_id = require_id(person_detail.person_id)
        person = self._person_service().repository.get_by_id(person_id)
        if person is None:
            msg = f"Person {person_id} was not found"
            raise LookupError(msg)
        return await self.generate_for_person(
            person,
            person_detail,
            context=context,
        )

    async def generate_for_person(
        self,
        person: Person,
        person_detail: PersonDetail,
        *,
        context: str | None = None,
        budgeted_context: ContextBudgetResult | None = None,
    ) -> PersonAssessment:
        """Generate and persist an assessment from prepared person details."""
        person_id = require_id(person.id)
        if person_detail.person_id != person_id:
            msg = "Person detail does not belong to the supplied person"
            raise ValueError(msg)
        budgeted = budgeted_context or await self.prepare_context(
            person_detail,
            additional_context=context,
        )
        content = await AssessmentAgent(
            food_repo=self._food_repository(),
            embedding_service=self._embedding_service(),
        ).run(budgeted.assessment_context)
        assessment = PersonAssessment(
            person_id=person_id,
            person=person,
            content=content,
            assessment_source=AssessmentSource.GENERATED,
            content_hash=self._content_hash(content),
            assessment_index=0,
            assessment_date=datetime.now(UTC).date(),
            created_by=ASSESSMENT_MODEL,
            status=StatusType.DRAFT,
            model_name=ASSESSMENT_MODEL,
        )
        return self.assessment_repository.create(assessment)

    async def prepare_context(
        self,
        person_detail: PersonDetail,
        *,
        additional_context: str | None = None,
    ) -> ContextBudgetResult:
        """Retrieve similar assessments and build the bounded agent context."""
        summary = person_detail.create_summary_text()
        relevant_assessments = await asyncio.to_thread(
            self._embedding_service().search_assessments,
            summary,
            top_k=_ASSESSMENT_MATCH_LIMIT,
        )
        return self.context_budgeter.budget(
            person_detail,
            relevant_assessments=relevant_assessments,
            additional_context=additional_context,
        )

    async def generate_many(
        self,
        requests: typing.Sequence[AssessmentGenerationRequest],
    ) -> list[PersonAssessment]:
        """Generate assessments once per unique facility/person pair."""
        assessments: list[PersonAssessment] = []
        seen: set[tuple[str | None, str]] = set()
        for request in requests:
            person_key = (
                request.facility_identifier,
                request.source_person_identifier,
            )
            if person_key in seen:
                continue
            seen.add(person_key)
            assessments.append(
                await self.generate(
                    request.source_person_identifier,
                    facility_identifier=request.facility_identifier,
                    context=request.context,
                ),
            )
        return assessments

    async def finalize(self, assessment_id: int) -> PersonAssessment | None:
        """Finalize an assessment and ensure its retrieval embedding exists."""
        assessment = self.assessment_repository.finalize(assessment_id)
        if assessment is not None:
            await self.embed_assessment(assessment)
        return assessment

    async def update(
        self,
        assessment_id: int,
        *,
        content: str | None = None,
        assessment_date: date | None = None,
        created_by: str | None = None,
        status: StatusType | None = None,
    ) -> PersonAssessment | None:
        """Apply assessment edits and replace a finalized content embedding."""
        assessment = self.assessment_repository.get_by_id(assessment_id)
        if assessment is None:
            return None
        content_changed = self._apply_updates(
            assessment,
            content=content,
            assessment_date=assessment_date,
            created_by=created_by,
            status=status,
        )
        embedding: list[float] | None = None
        embedding_model: str | None = None
        if content_changed and assessment.status is StatusType.FINALIZED:
            vector_service = self._embedding_service()
            embedding = await vector_service.get_embedding_async(assessment.content)
            embedding_model = vector_service.embedding_model
        return self.assessment_repository.update(
            assessment,
            embedding=embedding,
            model_name=embedding_model,
        )

    @staticmethod
    def _apply_updates(
        assessment: PersonAssessment,
        *,
        content: str | None,
        assessment_date: date | None,
        created_by: str | None,
        status: StatusType | None,
    ) -> bool:
        """Mutate supplied assessment fields and report whether content changed."""
        if content is not None:
            normalized_content = " ".join(content.split())
            if not normalized_content:
                message = "Assessment content cannot be empty"
                raise ValueError(message)
            assessment.content = content.strip()
            assessment.content_hash = AssessmentPipeline._content_hash(content)
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
        return content is not None

    async def embed_assessment(self, assessment: PersonAssessment) -> bool:
        """Create a missing embedding for a finalized assessment."""
        if assessment.status is not StatusType.FINALIZED:
            return False
        assessment_id = require_id(assessment.id)
        if self.assessment_repository.get_embedding(assessment_id) is not None:
            return False
        vector_service = self._embedding_service()
        embedding = await vector_service.get_embedding_async(assessment.content)
        self.assessment_repository.update(
            assessment,
            embedding=embedding,
            model_name=vector_service.embedding_model,
        )
        return True

    async def sync_assessments(self) -> AssessmentSyncResult:
        """Create imported assessments and embeddings from eligible notes."""
        result = AssessmentSyncResult()
        for note in self._progress_note_repository().get_all():
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
                if await self.embed_assessment(assessment):
                    result.embeddings_created += 1
                else:
                    result.embeddings_existing += 1
            except Exception:
                result.failed += 1
                logger.exception("Failed to synchronize progress note %s", note.id)
        return result

    async def sync(self) -> AssessmentSyncResult:
        """Run the historical-assessment synchronization workflow."""
        return await self.sync_assessments()

    @staticmethod
    def is_assessment_note(note: PersonProgressNote) -> bool:
        """Return whether a note type denotes nutrition documentation."""
        note_type = " ".join((note.note_type or "").casefold().split())
        return any(term in note_type for term in _NUTRITION_ASSESSMENT_TYPE_TERMS)

    @staticmethod
    def _build_assessment(note: PersonProgressNote) -> PersonAssessment:
        content = note.note_text
        if not content.strip():
            msg = f"Progress note {note.id} has no assessment text"
            raise ValueError(msg)
        creator = (note.author or "").strip() or "unknown"
        return PersonAssessment(
            person_id=note.person_id,
            source_progress_note_id=require_id(note.id),
            content=content,
            assessment_source=AssessmentSource.IMPORTED,
            content_hash=AssessmentPipeline._content_hash(content),
            assessment_date=note.note_date.date(),
            created_by=creator,
            status=StatusType.FINALIZED,
            finalized_at=note.note_date,
        )

    @staticmethod
    def _content_hash(content: str) -> str:
        return sha256(" ".join(content.split()).encode()).hexdigest()

    def _person_service(self) -> PersonService:
        if self.person_service is None:
            msg = "A person service is required for assessment generation"
            raise RuntimeError(msg)
        return self.person_service

    def _progress_note_repository(self) -> ProgressNoteRepo:
        if self.progress_note_repository is None:
            msg = "A progress-note repository is required for assessment sync"
            raise RuntimeError(msg)
        return self.progress_note_repository

    def _food_repository(self) -> FoodRepo:
        if self.food_repository is None:
            msg = "A food repository is required for assessment generation"
            raise RuntimeError(msg)
        return self.food_repository

    def _embedding_service(self) -> EmbeddingService:
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService(self.embedding_repository)
        return self.embedding_service


__all__ = [
    "AssessmentGenerationRequest",
    "AssessmentPipeline",
    "AssessmentSyncResult",
]
