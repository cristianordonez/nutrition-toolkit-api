"""Verify fact-domain routing is independent of extraction mechanism."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime

from sqlmodel import Session, SQLModel, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.models.ai_extraction import AIExtractedClinicalFact
from ntk.models.extracted_fact_create import (
    ClinicalFactPayload,
    EdemaPayload,
    ExtractedFactCreate,
    LabPayload,
    MealIntakePayload,
    OrderPayload,
    WeightPayload,
    WoundPayload,
)
from ntk.models.sql.clinical import (
    AI_CAPABLE_STRUCTURED_MODELS,
    DETERMINISTIC_FIRST_MODELS,
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentWeight,
    ResidentWound,
)
from ntk.models.sql.extracted_fact import ExtractedFact, ExtractionMethod
from ntk.models.sql.resident import Resident
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.resident_data.transform import (
    DOMAIN_MODEL_BY_FACT_TYPE,
    ExtractedFactTransformer,
)
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
        resident_id=1,
        payload=validated.payload,
        confidence=validated.confidence,
        confidence_reason=validated.confidence_reason,
        model_name=_AI_MODEL,
    )


def test_domain_model_categories_are_explicit() -> None:
    assert (
        ResidentWeight,
        ResidentLab,
        ResidentOrder,
    ) == DETERMINISTIC_FIRST_MODELS
    assert (
        ResidentEdema,
        ResidentMealIntake,
        ResidentWound,
    ) == AI_CAPABLE_STRUCTURED_MODELS
    assert {
        "clinical_fact": ResidentClinicalFact,
        "edema": ResidentEdema,
        "intake": ResidentMealIntake,
        "lab": ResidentLab,
        "order": ResidentOrder,
        "weight": ResidentWeight,
        "wound": ResidentWound,
    } == DOMAIN_MODEL_BY_FACT_TYPE


def test_typed_facts_route_to_domain_models_with_provenance(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document_path = tmp_path / "resident-facts.pdf"
    document_path.write_bytes(b"typed resident facts")

    with Session(engine) as session:
        resident = Resident(name="Resident")
        session.add(resident)
        session.commit()
        session.refresh(resident)
        resident_id = require_id(resident.id)

        deterministic_facts = [
            ExtractedFactCreate(
                resident_id=resident_id,
                payload=WeightPayload(
                    weight_lb=152.4,
                    measured_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
            ExtractedFactCreate(
                resident_id=resident_id,
                payload=LabPayload(
                    name="Albumin",
                    result="3.2",
                    observed_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
            ExtractedFactCreate(
                resident_id=resident_id,
                payload=OrderPayload(
                    summary="High-protein supplement",
                    revision_date=date(2026, 8, 30),
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
                    description="Resident reports feeling full early.",
                    observed_at=_OBSERVED_AT,
                ),
            ),
        ]
        for fact in ai_facts:
            fact.resident_id = resident_id

        transformed = ExtractedFactTransformer().transform(
            document_path,
            [*deterministic_facts, *ai_facts],
            extractor_name="RoutingTestExtractor",
        )
        ResidentRepo(session).load_transformed_documents([transformed])

        assert len(session.exec(select(ResidentWeight)).all()) == 1
        assert len(session.exec(select(ResidentLab)).all()) == 1
        assert len(session.exec(select(ResidentOrder)).all()) == 1
        assert len(session.exec(select(ResidentEdema)).all()) == 1
        assert len(session.exec(select(ResidentMealIntake)).all()) == 1
        assert len(session.exec(select(ResidentWound)).all()) == 1
        assert len(session.exec(select(ResidentClinicalFact)).all()) == 1

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

        context = ResidentRepo(session).get_assessment_records(resident_id)
        assert len(context.weights) == 1
        assert len(context.labs) == 1
        assert len(context.orders) == 1
        assert len(context.edema) == 1
        assert len(context.meal_intakes) == 1
        assert len(context.wounds) == 1
        assert len(context.clinical_facts) == 1
