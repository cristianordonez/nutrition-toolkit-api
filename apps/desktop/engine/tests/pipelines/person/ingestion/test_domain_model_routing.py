"""Verify fact-domain routing is independent of extraction mechanism."""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine, select

import engine.models.sql  # noqa: F401
from engine.models.ai_extraction import AIExtractedFact
from engine.models.clinical_fact_registry import FACT_DEFINITIONS
from engine.models.clinical_facts import (
    PersonClinicalFact,
    PersonLab,
    PersonSupplement,
    PersonWeight,
)
from engine.models.extracted_fact_create import (
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
from engine.models.sql.clinical_fact import ClinicalFact, ExtractionMethod
from engine.models.sql.clinical_source import ClinicalSource, SourceAuthority
from engine.models.sql.person import Person
from engine.pipelines.person.ingestion.transformer import ClinicalFactTransformer
from engine.repositories.person_repo import PersonRepo
from engine.utils.misc import require_id

if typing.TYPE_CHECKING:
    import pathlib

_OBSERVED_AT = datetime(2026, 8, 30, 12, tzinfo=UTC)
_AI_MODEL = "test-ai-extractor"


def _ai_fact(payload: object) -> ExtractedFactCreate:
    validated = AIExtractedFact.model_validate(
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
    assert FACT_DEFINITIONS["weight"].record_model is PersonWeight
    assert FACT_DEFINITIONS["lab"].record_model is PersonLab
    assert FACT_DEFINITIONS["clinical_observation"].record_model is PersonClinicalFact
    assert FACT_DEFINITIONS["supplement"].record_model is PersonSupplement
    assert "order" not in FACT_DEFINITIONS


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

        transformed = ClinicalFactTransformer().transform(
            document_path,
            [*deterministic_facts, *ai_facts],
            extractor_name="RoutingTestExtractor",
        )
        PersonRepo(session).load_transformed_documents([transformed])

        facts = list(session.exec(select(ClinicalFact)).all())
        assert {fact.fact_type for fact in facts} == {
            "weight",
            "lab",
            "supplement",
            "edema",
            "meal_intake",
            "wound",
            "clinical_observation",
        }
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
        assert all(fact.source is not None for fact in transformed.clinical_facts)

        context = PersonRepo(session).get_clinical_records(person_id)
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
    document_path = tmp_path / "medication-server.txt"
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

        transformed = ClinicalFactTransformer().transform(
            document_path,
            [api_fact],
            extractor_name="ExampleEmrMedicationAdapter",
        )
        PersonRepo(session).load_transformed_documents([transformed])

        fact = session.exec(select(ClinicalFact)).one()
        source = session.exec(select(ClinicalSource)).one()
        medication = PersonRepo(session).get_clinical_records(
            require_id(person.id),
        ).medications[0]
        assert medication.clinical_source_id == source.id
        assert fact.clinical_source_id == source.id
        assert fact.extraction_method is ExtractionMethod.API
        assert source.source_system == "example-emr"
        assert source.source_record_type == "medication"
        assert source.source_record_id == "MED-123"
        assert source.source_record_version == "7"
        assert source.source_authority is SourceAuthority.STRUCTURED_RECORD
