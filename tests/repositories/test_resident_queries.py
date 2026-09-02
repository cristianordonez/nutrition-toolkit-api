from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.resident import Resident, ResidentAssessment, ResidentWeight
from ntk.repositories.resident_repo import ResidentRepo


def test_resident_repo_queries_assessments_and_weights_by_resident_ids() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = Resident(name="First")
        second = Resident(name="Second")
        session.add_all([first, second])
        session.flush()
        assert first.id is not None
        assert second.id is not None
        session.add_all(
            [
                ResidentAssessment(
                    resident_id=first.id,
                    content="First assessment",
                    content_hash="first",
                    assessment_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
                    created_by="model",
                ),
                ResidentAssessment(
                    resident_id=second.id,
                    content="Second assessment",
                    content_hash="second",
                    assessment_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
                    created_by="model",
                ),
                ResidentWeight(
                    resident_id=first.id,
                    measured_at=datetime(2026, 8, 28, tzinfo=UTC),
                    weight_lb=150,
                ),
                ResidentWeight(
                    resident_id=second.id,
                    measured_at=datetime(2026, 8, 28, tzinfo=UTC),
                    weight_lb=160,
                ),
            ],
        )
        session.commit()
        repository = ResidentRepo(session)

        found_assessments = repository.get_assessments_by_resident_ids([first.id])
        found_weights = repository.get_weights_by_resident_ids([first.id])

    assert [item.content for item in found_assessments] == ["First assessment"]
    assert [item.weight_lb for item in found_weights] == [150]
