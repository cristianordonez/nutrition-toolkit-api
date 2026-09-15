from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from engine.models.sql.person import Person, PersonWeight
from engine.repositories.person_repo import PersonRepo


def test_person_repo_queries_weights_by_person_ids() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = Person(name="First")
        second = Person(name="Second")
        session.add_all([first, second])
        session.flush()
        assert first.id is not None
        assert second.id is not None
        session.add_all(
            [
                PersonWeight(
                    person_id=first.id,
                    measured_at=datetime(2026, 8, 28, tzinfo=UTC),
                    weight_lb=150,
                ),
                PersonWeight(
                    person_id=second.id,
                    measured_at=datetime(2026, 8, 28, tzinfo=UTC),
                    weight_lb=160,
                ),
            ],
        )
        session.commit()
        repository = PersonRepo(session)

        found_weights = repository.get_weights_by_person_ids([first.id])

    assert [item.weight_lb for item in found_weights] == [150]
