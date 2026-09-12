from __future__ import annotations

import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.extracted_fact_create import ExtractedFactCreate, WeightPayload
from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.models.sql.person import PersonWeight
from ntk.pipelines.person.ingestion.transformer import ExtractedFactTransformer
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib


@pytest.mark.parametrize("single_transaction", [False, True])
def test_overlapping_weight_history_upserts_existing_observation(
    tmp_path: pathlib.Path,
    *,
    single_transaction: bool,
) -> None:
    expected_weight = 121
    expected_fact_count = 2
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    first_path = tmp_path / "weights-first.pdf"
    second_path = tmp_path / "weights-second.pdf"
    first_path.write_bytes(b"first weight report")
    second_path.write_bytes(b"second weight report")
    measured_at = datetime(2026, 8, 24, 22, 17, tzinfo=UTC)

    with Session(engine) as session:
        repository = PersonRepo(session)
        facility_repository = FacilityRepo(session)
        resolver = FacilityResolver(facility_repository)
        resolver.register_trusted(name="Facility")
        person_service = PersonService(
            repository,
            resolver,
        )
        transformer = ExtractedFactTransformer(person_service)

        first = transformer.transform(
            first_path,
            [_weight_fact(measured_at, weight_lb=120, description="Wheelchair")],
            extractor_name="PccWeightHistoryExtractor",
        )
        if not single_transaction:
            repository.load_transformed_documents([first])

        second = transformer.transform(
            second_path,
            [_weight_fact(measured_at, weight_lb=121, description="Standing")],
            extractor_name="PccWeightHistoryExtractor",
        )
        if single_transaction:
            repository.load_transformed_documents([first, second])
        else:
            repository.load_transformed_documents([second])

        weights = list(session.exec(select(PersonWeight)).all())
        assert len(weights) == 1
        assert weights[0].weight_lb == expected_weight
        assert weights[0].description == "Standing"
        assert len(session.exec(select(ExtractedFact)).all()) == expected_fact_count


def _weight_fact(
    measured_at: datetime,
    *,
    weight_lb: float,
    description: str,
) -> ExtractedFactCreate:
    return ExtractedFactCreate(
        source_person_identifier="R-1",
        source_person_name="Person",
        facility_name="Facility",
        payload=WeightPayload(
            weight_lb=weight_lb,
            measured_at=measured_at,
            description=description,
        ),
        confidence=1,
    )
