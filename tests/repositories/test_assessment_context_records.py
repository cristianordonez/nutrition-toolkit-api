from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.clinical import ClinicalStatus, PersonDiet
from ntk.models.sql.person import (
    ClinicalFactType,
    ExtractionStatus,
    Person,
    PersonClinicalFact,
    PersonEdema,
    PersonLab,
    PersonMealIntake,
    PersonProgressNote,
    PersonWeight,
    PersonWound,
)
from ntk.repositories.person_repo import PersonRepo
from ntk.utils.misc import require_id


def test_assessment_records_are_recent_and_orders_are_current() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    older = datetime(2026, 7, 1, tzinfo=UTC)
    newer = datetime(2026, 8, 1, tzinfo=UTC)

    with Session(engine) as session:
        person = Person(name="Person")
        session.add(person)
        session.commit()
        session.refresh(person)
        person_id = require_id(person.id)
        session.add_all(
            [
                PersonWeight(
                    person_id=person_id,
                    measured_at=older,
                    weight_lb=150,
                ),
                PersonWeight(
                    person_id=person_id,
                    measured_at=newer,
                    weight_lb=145,
                ),
                PersonLab(
                    person_id=person_id,
                    name="Albumin",
                    result="3.2",
                    observed_at=newer,
                ),
                PersonDiet(
                    person_id=person_id,
                    diet_type="Renal",
                    status=ClinicalStatus.ACTIVE,
                    observed_at=newer,
                    state_key="current-diet",
                    extracted_fact_id=1,
                ),
                PersonProgressNote(
                    person_id=person_id,
                    note_date=newer,
                    note_text="Nutrition follow-up",
                    raw_text="Nutrition follow-up",
                    note_key="note-key",
                    extraction_status=ExtractionStatus.EXTRACTED,
                ),
                PersonWound(
                    person_id=person_id,
                    wound_number="1",
                    type="Pressure injury",
                    location="Sacrum",
                    observed_at=newer,
                ),
                PersonEdema(
                    person_id=person_id,
                    location="Lower extremities",
                    severity="2+",
                    observed_at=newer,
                ),
                PersonMealIntake(
                    person_id=person_id,
                    min_percent=50,
                    max_percent=75,
                    observed_at=newer,
                ),
                PersonClinicalFact(
                    person_id=person_id,
                    clinical_fact_type=ClinicalFactType.OBSERVATION,
                    observation_type="appetite",
                    description="Poor appetite",
                    observed_at=newer,
                ),
            ],
        )
        session.commit()

        records = PersonRepo(session).get_assessment_records(person_id)

        assert [weight.weight_lb for weight in records.weights] == [145, 150]
        assert [lab.name for lab in records.labs] == ["Albumin"]
        assert [diet.diet_type for diet in records.diets] == ["Renal"]
        assert [note.note_key for note in records.progress_notes] == ["note-key"]
        assert [wound.wound_number for wound in records.wounds] == ["1"]
        assert [item.location for item in records.edema] == ["Lower extremities"]
        assert [item.min_percent for item in records.meal_intakes] == [50]
        assert [fact.observation_type for fact in records.clinical_facts] == [
            "appetite",
        ]
