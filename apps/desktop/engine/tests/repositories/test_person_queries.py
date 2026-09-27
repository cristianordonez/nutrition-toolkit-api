from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from engine.models.clinical_fact_registry import fact_envelope
from engine.models.clinical_facts import PersonWeight
from engine.models.sql.clinical_fact import ClinicalFact
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo


def test_person_repo_queries_weights_by_person_ids() -> None:
    database = create_engine("sqlite://")
    SQLModel.metadata.create_all(database)

    with Session(database) as session:
        first = Person(name="First")
        second = Person(name="Second")
        session.add_all([first, second])
        session.flush()
        assert first.id is not None
        assert second.id is not None
        for person_id, weight_lb in ((first.id, 150), (second.id, 160)):
            record = PersonWeight(
                person_id=person_id,
                measured_at=datetime(2026, 8, 28, tzinfo=UTC),
                weight_lb=weight_lb,
            )
            session.add(
                ClinicalFact(
                    person_id=person_id,
                    fact_type="weight",
                    **fact_envelope(record, "weight"),
                ),
            )
        session.commit()

        found_weights = PersonRepo(session).get_weights_by_person_ids([first.id])

    assert [item.weight_lb for item in found_weights] == [150]
