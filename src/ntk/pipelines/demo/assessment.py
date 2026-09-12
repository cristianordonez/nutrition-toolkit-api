"""Transient document-to-assessment demo orchestration."""

from __future__ import annotations

import logging
import time
import typing
from datetime import UTC, date, datetime

from ntk.agents.assessment_agent import ASSESSMENT_MODEL, AssessmentAgent
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.models.demo_assessment import (
    DemoAssessmentResponse,
    DemoContextSummary,
    DemoDocumentIngestionSummary,
    DemoGeneratedAssessment,
    DemoIngestionSummary,
    DemoPersonSummary,
)
from ntk.models.sql.facility import Facility
from ntk.models.sql.person import Person
from ntk.pipelines.assessment.create.context_budgeter import (
    ContextBudgeter,
    ContextBudgetResult,
)
from ntk.pipelines.person.ingestion.pipeline import get_person_extractor
from ntk.pipelines.person.ingestion.transformer import ExtractedFactTransformer
from ntk.repositories.person_repo import PersonAssessmentRecords
from ntk.services.person.detail_builder import PersonDetailBuilder

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

    from ntk.models.extracted_fact_create import ExtractedFactCreate
    from ntk.models.person_detail import PersonDetail
    from ntk.repositories.food_repo import FoodRepo
    from ntk.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


_DEMO_UPLOAD_REQUIREMENTS = UploadRequirements(
    allowed_suffixes=frozenset({".csv", ".pdf", ".txt"}),
    file_description="PDF, CSV, or text file",
    directory_prefix="ntk-demo-assessment-",
    default_filename=lambda _index: "clinical-document.pdf",
    reject_empty=True,
)
_ASSESSMENT_MATCH_LIMIT = 5
_RECORDS_FIELD_BY_FACT_TYPE = {
    "allergy": "allergies",
    "appetite": "appetite_observations",
    "clinical_fact": "clinical_facts",
    "diagnosis": "diagnoses",
    "dialysis": "dialysis_records",
    "diet": "diets",
    "edema": "edema",
    "enteral_feeding": "enteral_feedings",
    "fluid_plan": "fluid_plans",
    "food_preference": "food_preferences",
    "gi_observation": "gi_observations",
    "intake": "meal_intakes",
    "lab": "labs",
    "medication": "medications",
    "misc_order": "misc_orders",
    "nutrition_goal": "nutrition_goals",
    "oral_feeding_status": "oral_feeding_status_history",
    "parenteral_nutrition": "parenteral_nutrition_records",
    "supplement": "supplements",
    "weight": "weights",
    "wound": "wounds",
}


class NoDemoFactsError(ValueError):
    """Raised when uploaded documents contain no extractable clinical facts."""


class _TransientPersonDetailBuilder:
    """Build PersonDetail from facts without resolving or persisting identity."""

    def __init__(self, detail_builder: PersonDetailBuilder) -> None:
        self.detail_builder = detail_builder

    def build(self, facts: Sequence[ExtractedFactCreate]) -> PersonDetail:
        """Normalize transient facts and calculate one in-memory detail model."""
        person = self._person(facts)
        records = PersonAssessmentRecords()
        for fact in facts:
            try:
                records_field = _RECORDS_FIELD_BY_FACT_TYPE[fact.payload.type]
            except KeyError as error:
                msg = f"Unsupported demo fact type: {fact.payload.type}"
                raise TypeError(msg) from error
            record = ExtractedFactTransformer.build_related_model(
                fact,
                person_id=0,
            )
            # These rows remain in memory. Do not expose a placeholder database ID.
            record.person_id = None  # ty: ignore[invalid-assignment]
            getattr(records, records_field).append(record)
        return self.detail_builder.build(person, records)

    @staticmethod
    def _person(facts: Sequence[ExtractedFactCreate]) -> Person:
        name = _first_fact_value(facts, "source_person_name")
        identifier = _first_fact_value(facts, "source_person_identifier")
        facility_name = _first_fact_value(facts, "facility_name")
        person = Person(
            name=name or identifier or "Demo person",
            date_of_birth=_first_fact_value(facts, "date_of_birth"),
            person_identifier=identifier,
            sex=_first_fact_value(facts, "sex"),
            height_in=_first_fact_value(facts, "height_in"),
        )
        if facility_name:
            person.facility = Facility(name=facility_name)
        return person


@typing.overload
def _first_fact_value(
    facts: Sequence[ExtractedFactCreate],
    field_name: typing.Literal[
        "facility_name",
        "sex",
        "source_person_identifier",
        "source_person_name",
    ],
) -> str | None: ...


@typing.overload
def _first_fact_value(
    facts: Sequence[ExtractedFactCreate],
    field_name: typing.Literal["date_of_birth"],
) -> date | None: ...


@typing.overload
def _first_fact_value(
    facts: Sequence[ExtractedFactCreate],
    field_name: typing.Literal["height_in"],
) -> float | None: ...


def _first_fact_value(
    facts: Sequence[ExtractedFactCreate],
    field_name: str,
) -> str | date | float | None:
    """Return the first non-empty source value without resolving an identity."""
    return typing.cast(
        "str | date | float | None",
        next(
            (
                value
                for fact in facts
                if (value := getattr(fact, field_name, None)) not in {None, ""}
            ),
            None,
        ),
    )


class DemoAssessmentPipeline:
    """Extract documents and generate an assessment entirely in memory."""

    def __init__(
        self,
        food_repository: FoodRepo,
        embedding_service: EmbeddingService,
        *,
        detail_builder: PersonDetailBuilder | None = None,
        context_budgeter: ContextBudgeter | None = None,
        assessment_agent: AssessmentAgent | None = None,
    ) -> None:
        """Store read-only tool dependencies and transient context builders."""
        self.embedding_service = embedding_service
        self.context_budgeter = context_budgeter or ContextBudgeter()
        self.detail_builder = _TransientPersonDetailBuilder(
            detail_builder or PersonDetailBuilder(),
        )
        self.assessment_agent = assessment_agent or AssessmentAgent(
            food_repo=food_repository,
            embedding_service=embedding_service,
        )

    async def run(self, upload: ReadableUpload) -> DemoAssessmentResponse:
        """Retain the single-upload entry point for existing callers."""
        return await self.run_uploads([upload])

    async def run_uploads(
        self,
        uploads: Sequence[ReadableUpload],
    ) -> DemoAssessmentResponse:
        """Materialize uploads temporarily and generate an unsaved assessment."""
        async with materialize_uploads(
            uploads,
            _DEMO_UPLOAD_REQUIREMENTS,
        ) as materialized:
            return await self.run_paths(materialized.paths)

    async def run_path(self, path: pathlib.Path) -> DemoAssessmentResponse:
        """Retain the single-path entry point for existing callers."""
        return await self.run_paths([path])

    async def run_paths(
        self,
        paths: Sequence[pathlib.Path],
    ) -> DemoAssessmentResponse:
        """Combine transient facts from every unique document into one context."""
        pipeline_started_at = time.perf_counter()
        paths_by_checksum = {
            ExtractedFactTransformer.document_checksum(path): path for path in paths
        }
        if not paths_by_checksum:
            msg = "At least one clinical document is required"
            raise ValueError(msg)

        facts: list[ExtractedFactCreate] = []
        document_summaries: list[DemoDocumentIngestionSummary] = []
        for path in paths_by_checksum.values():
            extraction_started_at = time.perf_counter()
            extractor = get_person_extractor(path)
            extract_for_demo = getattr(extractor, "extract_for_demo", None)
            document_facts = (
                await extract_for_demo()
                if callable(extract_for_demo)
                else await extractor.extract()
            )
            logger.info(
                "Demo document extraction completed: document=%s extractor=%s "
                "facts=%s duration_seconds=%.3f",
                path.name,
                type(extractor).__name__,
                len(document_facts),
                time.perf_counter() - extraction_started_at,
            )
            facts.extend(document_facts)
            document_summaries.append(
                DemoDocumentIngestionSummary(
                    document_type=type(extractor).__name__,
                    facts_extracted=len(document_facts),
                    facts_persisted=0,
                ),
            )
        if not facts:
            msg = "The uploaded documents did not contain extractable clinical facts"
            raise NoDemoFactsError(msg)

        detail_started_at = time.perf_counter()
        detail = self.detail_builder.build(facts)
        logger.info(
            "Demo detail construction completed: facts=%s duration_seconds=%.3f",
            len(facts),
            time.perf_counter() - detail_started_at,
        )
        context_started_at = time.perf_counter()
        budgeted = await self._prepare_context(detail)
        logger.info(
            "Demo context preparation completed: tokens=%s duration_seconds=%.3f",
            budgeted.final_token_count,
            time.perf_counter() - context_started_at,
        )
        assessment_started_at = time.perf_counter()
        content = await self.assessment_agent.run(budgeted.assessment_context)
        logger.info(
            "Demo assessment generation completed: duration_seconds=%.3f",
            time.perf_counter() - assessment_started_at,
        )
        response = DemoAssessmentResponse(
            ingestion=self._ingestion_summary(document_summaries),
            person=DemoPersonSummary.from_detail(detail),
            detail=detail,
            context=DemoContextSummary(
                raw_token_count=budgeted.raw_token_count,
                final_token_count=budgeted.final_token_count,
                tokens_removed=budgeted.tokens_removed,
                token_reduction_percent=budgeted.token_reduction_percent,
                omitted_record_counts=budgeted.omitted_record_counts,
            ),
            assessment=DemoGeneratedAssessment.from_content(
                content,
                person_id=detail.person_id,
                model_name=ASSESSMENT_MODEL,
                created_at=datetime.now(UTC),
            ),
        )
        logger.info(
            "Demo assessment pipeline completed: documents=%s facts=%s "
            "duration_seconds=%.3f",
            len(document_summaries),
            len(facts),
            time.perf_counter() - pipeline_started_at,
        )
        return response

    async def _prepare_context(self, detail: PersonDetail) -> ContextBudgetResult:
        relevant_assessments = await self.embedding_service.search_assessments_async(
            detail.create_summary_text(),
            top_k=_ASSESSMENT_MATCH_LIMIT,
        )
        return self.context_budgeter.budget(
            detail,
            relevant_assessments=relevant_assessments,
        )

    @staticmethod
    def _ingestion_summary(
        documents: Sequence[DemoDocumentIngestionSummary],
    ) -> DemoIngestionSummary:
        single = documents[0] if len(documents) == 1 else None
        return DemoIngestionSummary(
            documents=list(documents),
            document_type=single.document_type if single is not None else None,
            facts_extracted=sum(item.facts_extracted for item in documents),
            facts_persisted=0,
        )


__all__ = ["DemoAssessmentPipeline", "NoDemoFactsError"]
