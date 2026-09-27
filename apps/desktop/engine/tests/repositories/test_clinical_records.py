from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from engine.models.extracted_fact_create import (
    ClinicalFactPayload,
    DietPayload,
    EdemaPayload,
    ExtractedFactCreate,
    LabPayload,
    MealIntakePayload,
    WeightPayload,
    WoundPayload,
)
from engine.models.sql.clinical_source import ClinicalSource, ClinicalSourceKind
from engine.models.sql.person import Person
from engine.pipelines.person.ingestion.transformer import ClinicalFactTransformer
from engine.repositories.person_repo import PersonRepo
from engine.utils.misc import require_id


def test_assessment_records_are_recent_and_orders_are_current(tmp_path) -> None:  # noqa: ANN001
    database = create_engine("sqlite://")
    SQLModel.metadata.create_all(database)
    older = datetime(2026, 7, 1, tzinfo=UTC)
    newer = datetime(2026, 8, 1, tzinfo=UTC)
    path = tmp_path / "clinical.txt"
    path.write_text("Clinical source material", encoding="utf-8")

    with Session(database) as session:
        person = Person(name="Person")
        session.add(person)
        session.commit()
        session.refresh(person)
        person_id = require_id(person.id)
        facts = [
            WeightPayload(measured_at=older, weight_lb=150),
            WeightPayload(measured_at=newer, weight_lb=145),
            LabPayload(name="Albumin", result="3.2", observed_at=newer),
            DietPayload(diet_type="Renal", status="active", observed_at=newer),
            WoundPayload(
                wound_number="1",
                wound_type="Pressure injury",
                location="Sacrum",
                observed_at=newer,
            ),
            EdemaPayload(
                location="Lower extremities",
                severity="2+",
                observed_at=newer,
            ),
            MealIntakePayload(
                min_percent=50,
                max_percent=75,
                observed_at=newer,
            ),
            ClinicalFactPayload(
                clinical_fact_type="observation",
                observation_type="appetite",
                description="Poor appetite",
                observed_at=newer,
            ),
        ]
        transformed = ClinicalFactTransformer().transform(
            path,
            [
                ExtractedFactCreate(person_id=person_id, payload=fact, confidence=1)
                for fact in facts
            ],
            extractor_name="TestExtractor",
        )
        note = ClinicalSource(
            person_id=person_id,
            source_kind=ClinicalSourceKind.PROGRESS_NOTE,
            source_key="note-key",
            content="Nutrition follow-up",
            raw_content="Nutrition follow-up",
            effective_at=newer,
        )
        transformed.clinical_sources.append(note)
        PersonRepo(session).load_transformed_documents([transformed])

        records = PersonRepo(session).get_clinical_records(person_id)

        assert [weight.weight_lb for weight in records.weights] == [145, 150]
        assert [lab.name for lab in records.labs] == ["Albumin"]
        assert [diet.diet_type for diet in records.diets] == ["renal"]
        assert [source.source_key for source in records.clinical_notes] == ["note-key"]
        assert [wound.wound_number for wound in records.wounds] == ["1"]
        assert [item.location for item in records.edema] == ["Lower extremities"]
        assert [item.min_percent for item in records.meal_intakes] == [50]
        assert [fact.observation_type for fact in records.clinical_facts] == [
            "appetite",
        ]
