from __future__ import annotations

import typing
from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.extracted_fact_create import (
    EdemaPayload,
    ExtractedFactCreate,
    FactPayload,
    LabPayload,
    OrderPayload,
)
from ntk.models.sql.resident import ResidentEdema, ResidentLab, ResidentOrder
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.resident_data.resident_resolver import ResidentResolver
from ntk.services.resident_data.transform import ExtractedFactTransformer

if typing.TYPE_CHECKING:
    import pathlib

_OBSERVED_AT = datetime(2026, 8, 24, 22, 17, tzinfo=UTC)


@pytest.mark.parametrize(
    ("first_payload", "second_payload", "model", "field_name", "expected"),
    [
        (
            LabPayload(name="Albumin", result="3.0", observed_at=_OBSERVED_AT),
            LabPayload(name="Albumin", result="3.2", observed_at=_OBSERVED_AT),
            ResidentLab,
            "result",
            "3.2",
        ),
        (
            OrderPayload(
                summary="Renal diet",
                status="Active",
                revision_date=date(2026, 8, 1),
            ),
            OrderPayload(
                summary="Renal diet",
                status="Inactive",
                revision_date=date(2026, 8, 1),
            ),
            ResidentOrder,
            "status",
            "Inactive",
        ),
        (
            EdemaPayload(
                location="Lower extremities",
                severity="1+",
                observed_at=_OBSERVED_AT,
            ),
            EdemaPayload(
                location="Lower extremities",
                severity="2+",
                observed_at=_OBSERVED_AT,
            ),
            ResidentEdema,
            "severity",
            "2+",
        ),
    ],
)
def test_constrained_incremental_fact_is_upserted(  # noqa: PLR0913
    tmp_path: pathlib.Path,
    first_payload: FactPayload,
    second_payload: FactPayload,
    model: type[SQLModel],
    field_name: str,
    expected: object,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    first_path = tmp_path / "first.pdf"
    second_path = tmp_path / "second.pdf"
    first_path.write_bytes(b"first report")
    second_path.write_bytes(b"second report")

    with Session(engine) as session:
        repository = ResidentRepo(session)
        transformer = ExtractedFactTransformer(
            ResidentResolver(
                resident_repository=repository,
                facility_repository=FacilityRepo(session),
                stay_repository=ResidentFacilityStayRepo(session),
            ),
        )
        first = transformer.transform(
            first_path,
            [_fact(first_payload)],
            extractor_name="IncrementalExtractor",
        )
        second = transformer.transform(
            second_path,
            [_fact(second_payload)],
            extractor_name="IncrementalExtractor",
        )

        repository.load_transformed_documents([first, second])

        records = list(session.exec(select(model)).all())
        assert len(records) == 1
        assert getattr(records[0], field_name) == expected


def _fact(payload: FactPayload) -> ExtractedFactCreate:
    return ExtractedFactCreate(
        facility_resident_identifier="R-1",
        resident_name="Resident",
        facility_name="Facility",
        payload=payload,
        confidence=1,
    )
