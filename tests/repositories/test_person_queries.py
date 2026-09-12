from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.person import Person, PersonAssessment, PersonWeight
from ntk.repositories.person_repo import PersonRepo


def test_person_repo_queries_assessments_and_weights_by_person_ids() -> None:
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
                PersonAssessment(
                    person_id=first.id,
                    content="First assessment",
                    content_hash="first",
                    assessment_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
                    created_by="model",
                ),
                PersonAssessment(
                    person_id=second.id,
                    content="Second assessment",
                    content_hash="second",
                    assessment_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
                    created_by="model",
                ),
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

        found_assessments = repository.get_assessments_by_person_ids([first.id])
        found_weights = repository.get_weights_by_person_ids([first.id])

    assert [item.content for item in found_assessments] == ["First assessment"]
    assert [item.weight_lb for item in found_weights] == [150]
