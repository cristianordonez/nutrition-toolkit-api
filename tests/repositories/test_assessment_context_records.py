from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.resident import (
    ClinicalFactType,
    ExtractionStatus,
    Resident,
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentProgressNote,
    ResidentWeight,
    ResidentWound,
)
from ntk.repositories.resident_repo import ResidentRepo
from ntk.utils.misc import require_id


def test_assessment_records_are_recent_and_orders_are_current() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    older = datetime(2026, 7, 1, tzinfo=UTC)
    newer = datetime(2026, 8, 1, tzinfo=UTC)

    with Session(engine) as session:
        resident = Resident(name="Resident")
        session.add(resident)
        session.commit()
        session.refresh(resident)
        resident_id = require_id(resident.id)
        session.add_all(
            [
                ResidentWeight(
                    resident_id=resident_id,
                    measured_at=older,
                    weight_lb=150,
                ),
                ResidentWeight(
                    resident_id=resident_id,
                    measured_at=newer,
                    weight_lb=145,
                ),
                ResidentLab(
                    resident_id=resident_id,
                    name="Albumin",
                    result="3.2",
                    observed_at=newer,
                ),
                ResidentOrder(
                    resident_id=resident_id,
                    summary="Renal diet",
                    status="Active",
                ),
                ResidentOrder(
                    resident_id=resident_id,
                    summary="Old supplement",
                    status="Inactive",
                ),
                ResidentProgressNote(
                    resident_id=resident_id,
                    note_date=newer,
                    note_text="Nutrition follow-up",
                    raw_text="Nutrition follow-up",
                    note_key="note-key",
                    extraction_status=ExtractionStatus.EXTRACTED,
                ),
                ResidentWound(
                    resident_id=resident_id,
                    wound_number="1",
                    type="Pressure injury",
                    location="Sacrum",
                    observed_at=newer,
                ),
                ResidentEdema(
                    resident_id=resident_id,
                    location="Lower extremities",
                    severity="2+",
                    observed_at=newer,
                ),
                ResidentMealIntake(
                    resident_id=resident_id,
                    min_percent=50,
                    max_percent=75,
                    observed_at=newer,
                ),
                ResidentClinicalFact(
                    resident_id=resident_id,
                    clinical_fact_type=ClinicalFactType.OBSERVATION,
                    observation_type="appetite",
                    description="Poor appetite",
                    observed_at=newer,
                ),
            ],
        )
        session.commit()

        records = ResidentRepo(session).get_assessment_records(resident_id)

        assert [weight.weight_lb for weight in records.weights] == [145, 150]
        assert [lab.name for lab in records.labs] == ["Albumin"]
        assert [order.summary for order in records.orders] == ["Renal diet"]
        assert [note.note_key for note in records.progress_notes] == ["note-key"]
        assert [wound.wound_number for wound in records.wounds] == ["1"]
        assert [item.location for item in records.edema] == ["Lower extremities"]
        assert [item.min_percent for item in records.meal_intakes] == [50]
        assert [fact.observation_type for fact in records.clinical_facts] == [
            "appetite",
        ]
