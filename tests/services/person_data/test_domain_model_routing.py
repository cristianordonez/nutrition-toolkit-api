"""Verify fact-domain routing is independent of extraction mechanism."""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.models.ai_extraction import AIExtractedClinicalFact
from ntk.models.extracted_fact_create import (
    ClinicalFactPayload,
    EdemaPayload,
    ExtractedFactCreate,
    LabPayload,
    MealIntakePayload,
    MedicationPayload,
    SupplementPayload,
    WeightPayload,
    WoundPayload,
)
from ntk.models.sql.clinical import (
    AI_CAPABLE_STRUCTURED_MODELS,
    DETERMINISTIC_FIRST_MODELS,
    PersonClinicalFact,
    PersonEdema,
    PersonLab,
    PersonMealIntake,
    PersonMedication,
    PersonSupplement,
    PersonWeight,
    PersonWound,
)
from ntk.models.sql.document import DocumentSource, SourceAuthority
from ntk.models.sql.extracted_fact import ExtractedFact, ExtractionMethod
from ntk.models.sql.person import Person
from ntk.pipelines.person.ingestion.transformer import (
    DOMAIN_MODEL_BY_FACT_TYPE,
    ExtractedFactTransformer,
)
from ntk.repositories.person_repo import PersonRepo
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    import pathlib

_OBSERVED_AT = datetime(2026, 8, 30, 12, tzinfo=UTC)
_AI_MODEL = "test-ai-extractor"


def _ai_fact(payload: object) -> ExtractedFactCreate:
    validated = AIExtractedClinicalFact.model_validate(
        {
            "payload": payload,
            "confidence": 0.9,
            "confidence_reason": "Explicitly documented",
        },
    )
    return ExtractedFactCreate(
        person_id=1,
        payload=validated.payload,
        confidence=validated.confidence,
        confidence_reason=validated.confidence_reason,
        model_name=_AI_MODEL,
        extraction_method=ExtractionMethod.AI,
    )


def test_domain_model_categories_are_explicit() -> None:
    assert (PersonWeight, PersonLab) == DETERMINISTIC_FIRST_MODELS
    assert {
        PersonEdema,
        PersonMealIntake,
        PersonSupplement,
        PersonWound,
    }.issubset(AI_CAPABLE_STRUCTURED_MODELS)
    assert DOMAIN_MODEL_BY_FACT_TYPE["clinical_fact"] is PersonClinicalFact
    assert DOMAIN_MODEL_BY_FACT_TYPE["supplement"] is PersonSupplement
    assert "order" not in DOMAIN_MODEL_BY_FACT_TYPE


def test_typed_facts_route_to_domain_models_with_provenance(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document_path = tmp_path / "person-facts.pdf"
    document_path.write_bytes(b"typed person facts")

    with Session(engine) as session:
        person = Person(name="Person")
        session.add(person)
        session.commit()
        session.refresh(person)
        person_id = require_id(person.id)

        deterministic_facts = [
            ExtractedFactCreate(
                person_id=person_id,
                payload=WeightPayload(
                    weight_lb=152.4,
                    measured_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
            ExtractedFactCreate(
                person_id=person_id,
                payload=LabPayload(
                    name="Albumin",
                    result="3.2",
                    observed_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
            ExtractedFactCreate(
                person_id=person_id,
                payload=SupplementPayload(
                    product_name="ProStat",
                    observed_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
        ]
        ai_facts = [
            _ai_fact(
                EdemaPayload(
                    location="Bilateral lower extremities",
                    severity="2+",
                    observed_at=_OBSERVED_AT,
                ),
            ),
            _ai_fact(
                MealIntakePayload(
                    min_percent=25,
                    max_percent=50,
                    observed_at=_OBSERVED_AT,
                ),
            ),
            _ai_fact(
                WoundPayload(
                    wound_type="Pressure injury",
                    location="Sacrum",
                    stage="3",
                    observed_at=_OBSERVED_AT,
                ),
            ),
            _ai_fact(
                ClinicalFactPayload(
                    clinical_fact_type="observation",
                    observation_type="early_satiety",
                    description="Person reports feeling full early.",
                    observed_at=_OBSERVED_AT,
                ),
            ),
        ]
        for fact in ai_facts:
            fact.person_id = person_id

        transformed = ExtractedFactTransformer().transform(
            document_path,
            [*deterministic_facts, *ai_facts],
            extractor_name="RoutingTestExtractor",
        )
        PersonRepo(session).load_transformed_documents([transformed])

        assert len(session.exec(select(PersonWeight)).all()) == 1
        assert len(session.exec(select(PersonLab)).all()) == 1
        assert len(session.exec(select(PersonSupplement)).all()) == 1
        assert len(session.exec(select(PersonEdema)).all()) == 1
        assert len(session.exec(select(PersonMealIntake)).all()) == 1
        assert len(session.exec(select(PersonWound)).all()) == 1
        assert len(session.exec(select(PersonClinicalFact)).all()) == 1

        facts = list(session.exec(select(ExtractedFact)).all())
        deterministic = [fact for fact in facts if fact.model_name is None]
        ai_extracted = [fact for fact in facts if fact.model_name == _AI_MODEL]
        assert len(deterministic) == 3  # noqa: PLR2004
        assert len(ai_extracted) == 4  # noqa: PLR2004
        assert all(
            fact.extraction_method is ExtractionMethod.DETERMINISTIC
            for fact in deterministic
        )
        assert all(
            fact.extraction_method is ExtractionMethod.AI for fact in ai_extracted
        )
        assert all(
            record.extracted_fact is not None for record in transformed.related_models
        )

        context = PersonRepo(session).get_assessment_records(person_id)
        assert len(context.weights) == 1
        assert len(context.labs) == 1
        assert len(context.supplements) == 1
        assert len(context.edema) == 1
        assert len(context.meal_intakes) == 1
        assert len(context.wounds) == 1
        assert len(context.clinical_facts) == 1


def test_api_fact_uses_the_same_normalization_and_provenance_path(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document_path = tmp_path / "medication-api.txt"
    document_path.write_text("canonical API medication response", encoding="utf-8")

    with Session(engine) as session:
        person = Person(name="Person")
        session.add(person)
        session.commit()
        session.refresh(person)
        api_fact = ExtractedFactCreate(
            person_id=require_id(person.id),
            payload=MedicationPayload(
                name="Lasix",
                dose=40,
                dose_unit="mg",
                frequency="BID",
                status="active",
                observed_at=_OBSERVED_AT,
            ),
            confidence=1,
            extraction_method=ExtractionMethod.API,
            source_system="example-emr",
            source_record_type="medication",
            source_record_id="MED-123",
            source_record_version="7",
            source_endpoint="/persons/1/medications",
            source_authority=SourceAuthority.STRUCTURED_RECORD,
        )

        transformed = ExtractedFactTransformer().transform(
            document_path,
            [api_fact],
            extractor_name="ExampleEmrMedicationAdapter",
        )
        PersonRepo(session).load_transformed_documents([transformed])

        medication = session.exec(select(PersonMedication)).one()
        fact = session.exec(select(ExtractedFact)).one()
        source = session.exec(select(DocumentSource)).one()
        assert medication.extracted_fact_id == fact.id
        assert fact.extraction_method is ExtractionMethod.API
        assert source.source_system == "example-emr"
        assert source.source_record_type == "medication"
        assert source.source_record_id == "MED-123"
        assert source.source_record_version == "7"
        assert source.source_authority is SourceAuthority.STRUCTURED_RECORD
