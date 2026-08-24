from __future__ import annotations

from datetime import UTC, date
from uuid import UUID, uuid4

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator
from sqlmodel import Session, create_engine

from ntk.models.sql.resident import (
    Resident,
    ResidentSnapshot,
    ResidentSnapshotAssessment,
)

_CURRENT_WEIGHT = 120.5


def test_resident_snapshot_models_use_expected_tables_and_foreign_keys() -> None:
    resident_table = Resident.__table__  # ty: ignore[unresolved-attribute]
    snapshot_table = ResidentSnapshot.__table__  # ty: ignore[unresolved-attribute]
    assessment_table = ResidentSnapshotAssessment.__table__  # ty: ignore[unresolved-attribute]

    assert resident_table.name == "resident"
    assert snapshot_table.name == "resident_snapshot"
    assert assessment_table.name == "resident_snapshot_assessment"
    assert {
        foreign_key.target_fullname
        for foreign_key in snapshot_table.c.resident_id.foreign_keys
    } == {"resident.id"}
    assert {
        foreign_key.target_fullname
        for foreign_key in assessment_table.c.resident_snapshot_id.foreign_keys
    } == {"resident_snapshot.id"}


def test_resident_snapshot_defaults_support_incomplete_extracted_data() -> None:
    resident = Resident(facility_id=uuid4())
    snapshot = ResidentSnapshot(resident_id=resident.id)
    assessment = ResidentSnapshotAssessment(
        resident_snapshot_id=snapshot.id,
        content="Nutrition assessment",
        model_name="gpt-4.1",
    )

    assert isinstance(resident.id, UUID)
    assert resident.created_at.tzinfo is UTC
    assert snapshot.payload == {}
    assert snapshot.weight_history == []
    assert snapshot.medications == []
    assert snapshot.latest_labs == []
    assert snapshot.past_medical_history == []
    assert snapshot.supplements == []
    assert snapshot.allergies == []
    assert snapshot.diagnoses == []
    assert snapshot.wounds == []
    assert snapshot.edema.present is None
    assert snapshot.edema.locations == []
    assert snapshot.notes == []
    assert snapshot.diet_restrictions == []
    assert snapshot.food_preferences == []
    assert snapshot.comparison == {}
    assert snapshot.current_weight is None
    assert assessment.resident_snapshot_id == snapshot.id
    assert assessment.created_at.tzinfo is UTC


def test_resident_snapshot_preserves_structured_clinical_fields() -> None:
    snapshot = ResidentSnapshot.model_validate(
        {
            "resident_id": uuid4(),
            "payload": {"source": "pcc"},
            "current_weight": _CURRENT_WEIGHT,
            "weight_date": date(2026, 8, 21),
            "bmi": 22.0,
            "weight_history": [{"date": "2026-07-21", "weight_lb": 130}],
            "medications": [{"name": "Metformin", "frequency": "BID"}],
            "diet": "CCD",
            "diet_texture": "mechanical soft",
            "liquid_consistency": "nectar thick",
            "diet_restrictions": ["concentrated sweets"],
            "food_preferences": ["yogurt"],
            "tubefeed_order": {
                "formula": "Glucerna 1.5",
                "rate": "75 mL/hr",
            },
            "latest_labs": [{"name": "A1c", "value": "7.2"}],
            "latest_labs_date": date(2026, 8, 21),
            "age": 82,
            "gender": "female",
            "height": 62.0,
            "past_medical_history": ["T2DM"],
            "supplements": [{"name": "Glucerna", "frequency": "QD"}],
            "allergies": ["shellfish"],
            "diagnoses": [{"name": "T2DM"}],
            "wounds": [
                {
                    "type": "pressure injury",
                    "location": "sacrum",
                    "stage": "3",
                },
            ],
            "edema": {"present": True, "severity": "1+"},
            "notes": [{"date": "2026-08-21", "note": "Intake improved."}],
            "dialysis": True,
            "dialysis_dry_weight": 118.0,
            "dialysis_target_weight": 117.0,
            "admission_date": date(2025, 1, 1),
            "readmission_date": date(2026, 8, 1),
            "comparison": {"weight": "130 lb -> 120.5 lb; -7.3%"},
        },
    )

    assert snapshot.current_weight == _CURRENT_WEIGHT
    assert snapshot.latest_labs_date == date(2026, 8, 21)
    assert snapshot.medications[0].name == "Metformin"
    assert snapshot.supplements[0].frequency == "QD"
    assert snapshot.tubefeed_order is not None
    assert snapshot.tubefeed_order.formula == "Glucerna 1.5"
    assert snapshot.notes[0].note == "Intake improved."
    assert snapshot.comparison["weight"].endswith("-7.3%")
    for field_name in (
        "payload",
        "medications",
        "weight_history",
        "diet_restrictions",
        "food_preferences",
        "tubefeed_order",
        "latest_labs",
        "past_medical_history",
        "supplements",
        "allergies",
        "diagnoses",
        "wounds",
        "edema",
        "notes",
        "comparison",
    ):
        column_type = ResidentSnapshot.__table__.c[field_name].type  # ty: ignore[unresolved-attribute]
        assert isinstance(column_type, (JSON, TypeDecorator))


def test_resident_snapshot_restores_typed_json_after_database_load() -> None:
    engine = create_engine("sqlite://")
    Resident.__table__.create(engine)  # ty: ignore[unresolved-attribute]
    ResidentSnapshot.__table__.create(engine)  # ty: ignore[unresolved-attribute]
    resident = Resident(facility_id=uuid4())
    snapshot = ResidentSnapshot.model_validate(
        {
            "resident_id": resident.id,
            "medications": [{"name": "Metformin"}],
            "tubefeed_order": {"formula": "Glucerna 1.5"},
            "edema": {"present": True},
            "notes": [{"note": "Meal intake improved."}],
        },
    )

    with Session(engine) as session:
        session.add(resident)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

    assert snapshot.medications[0].name == "Metformin"
    assert snapshot.tubefeed_order is not None
    assert snapshot.tubefeed_order.formula == "Glucerna 1.5"
    assert snapshot.edema.present is True
    assert snapshot.notes[0].note == "Meal intake improved."
