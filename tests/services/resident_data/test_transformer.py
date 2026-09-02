from __future__ import annotations

import hashlib
import typing
from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

import ntk.models.sql  # noqa: F401
from ntk.models.extracted_fact_create import (
    ClinicalFactPayload,
    EdemaPayload,
    ExtractedFactCreate,
    FactPayload,
    LabPayload,
    MealIntakePayload,
    OrderPayload,
    WeightPayload,
    WoundPayload,
)
from ntk.models.sql.document import DocumentSourceType
from ntk.models.sql.resident import (
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentWeight,
    ResidentWound,
)
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.resident_data.resident_resolver import (
    ResidentResolution,
    ResidentResolver,
)
from ntk.services.resident_data.transform import ExtractedFactTransformer

if typing.TYPE_CHECKING:
    import pathlib

_OBSERVED_AT = datetime(2026, 8, 27, tzinfo=UTC)


class StubResidentResolver:
    def __init__(self, resident_ids: dict[str, int]) -> None:
        self.resident_ids = resident_ids

    def resolve_or_create_resident(
        self,
        *,
        facility_resident_identifier: str | None = None,
        **_identity: object,
    ) -> ResidentResolution:
        if facility_resident_identifier is None:
            msg = "facility_resident_identifier is required"
            raise ValueError(msg)
        resident_id = self.resident_ids.get(facility_resident_identifier)
        if resident_id is None:
            msg = f"Resident {facility_resident_identifier!r} was not found"
            raise ValueError(msg)
        return ResidentResolution(resident_id=resident_id)


def stub_resolver(resident_ids: dict[str, int]) -> ResidentResolver:
    return typing.cast("ResidentResolver", StubResidentResolver(resident_ids))


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (WeightPayload(weight_lb=130), ResidentWeight),
        (OrderPayload(summary="Renal diet"), ResidentOrder),
        (
            LabPayload(name="Albumin", result="3.0", observed_at=_OBSERVED_AT),
            ResidentLab,
        ),
        (
            WoundPayload(
                wound_type="Pressure injury",
                location="Sacrum",
                observed_at=_OBSERVED_AT,
            ),
            ResidentWound,
        ),
        (
            EdemaPayload(location="Lower extremities", observed_at=_OBSERVED_AT),
            ResidentEdema,
        ),
        (
            MealIntakePayload(
                min_percent=50,
                max_percent=75,
                observed_at=_OBSERVED_AT,
            ),
            ResidentMealIntake,
        ),
        (
            ClinicalFactPayload(
                clinical_fact_type="observation",
                observation_type="swallowing",
                observed_at=_OBSERVED_AT,
            ),
            ResidentClinicalFact,
        ),
    ],
)
def test_transformer_builds_provenance_fact_and_related_model(
    tmp_path: pathlib.Path,
    payload: FactPayload,
    expected_type: type[object],
) -> None:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"resident report")
    resident_id = 7
    create = ExtractedFactCreate(
        facility_resident_identifier="RES1",
        payload=payload,
        confidence=0.9,
        confidence_reason="test",
    )

    transformed = ExtractedFactTransformer(
        stub_resolver({"RES1": resident_id}),
    ).transform(
        path,
        [create],
        extractor_name="TestExtractor",
    )

    assert transformed.document.filename == "report.pdf"
    assert transformed.document.file_type == "application/pdf"
    assert transformed.document.checksum == (
        f"sha256:{hashlib.sha256(b'resident report').hexdigest()}"
    )
    assert transformed.document.document_type == "TestExtractor"
    assert len(transformed.document_sources) == 1
    source = transformed.document_sources[0]
    assert source.document_id == transformed.document.id
    assert source.source_type is DocumentSourceType.PDF
    assert len(source.evidence_hash) == 64  # noqa: PLR2004

    assert len(transformed.extracted_facts) == 1
    fact = transformed.extracted_facts[0]
    assert fact.source_id == source.id
    assert fact.resident_id == resident_id
    assert fact.fact_type == payload.type
    assert fact.extractor_name == "TestExtractor"
    assert fact.fact_key
    assert fact.transformed_at is not None

    assert len(transformed.related_models) == 1
    related = transformed.related_models[0]
    assert isinstance(related, expected_type)
    assert related.resident_id == resident_id
    assert related.extracted_fact_id == fact.id
    assert related.extracted_fact is fact


def test_transformer_preserves_effective_time(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "weights.csv"
    path.write_text("weight", encoding="utf-8")
    measured_at = datetime(2026, 8, 27, 12, 30, tzinfo=UTC)
    create = ExtractedFactCreate(
        facility_resident_identifier="RES1",
        payload=WeightPayload(weight_lb=130, measured_at=measured_at),
        confidence=1.0,
    )

    transformed = ExtractedFactTransformer(stub_resolver({"RES1": 7})).transform(
        path,
        [create],
        extractor_name="PccWeightHistoryExtractor",
    )

    assert transformed.extracted_facts[0].effective_at == measured_at
    assert typing.cast("ResidentWeight", transformed.related_models[0]).measured_at == (
        measured_at
    )


def test_transformer_normalizes_missing_edema_location(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "notes.pdf"
    path.write_bytes(b"edema without a documented location")
    create = ExtractedFactCreate(
        facility_resident_identifier="RES1",
        payload=EdemaPayload(location=None, observed_at=_OBSERVED_AT),
        confidence=1.0,
    )

    transformed = ExtractedFactTransformer(stub_resolver({"RES1": 7})).transform(
        path,
        [create],
        extractor_name="PccProgressNoteExtractor",
    )

    edema = typing.cast("ResidentEdema", transformed.related_models[0])
    assert edema.location == "Unspecified"


def test_transformer_normalizes_missing_wound_location(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "notes.pdf"
    path.write_bytes(b"wound without a documented location")
    create = ExtractedFactCreate(
        facility_resident_identifier="RES1",
        payload=WoundPayload(
            wound_type="Pressure injury",
            location=None,
            observed_at=_OBSERVED_AT,
        ),
        confidence=1.0,
    )

    transformed = ExtractedFactTransformer(stub_resolver({"RES1": 7})).transform(
        path,
        [create],
        extractor_name="PccProgressNotesExtractor",
    )

    wound = typing.cast("ResidentWound", transformed.related_models[0])
    assert wound.location == "Unspecified"


def test_transformer_persists_deterministic_resident_demographics(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    path = tmp_path / "weights.pdf"
    path.write_bytes(b"resident demographics")

    with Session(engine) as session:
        resolver = ResidentResolver(
            resident_repository=ResidentRepo(session),
            facility_repository=FacilityRepo(session),
            stay_repository=ResidentFacilityStayRepo(session),
        )

        ExtractedFactTransformer(resolver).transform(
            path,
            [
                ExtractedFactCreate(
                    facility_name="Facility",
                    facility_resident_identifier="RES1",
                    resident_name="Resident",
                    date_of_birth=date(1946, 2, 1),
                    sex="Female",
                    height_in=64.5,
                    payload=WeightPayload(weight_lb=130),
                    confidence=1,
                ),
            ],
            extractor_name="PccWeightHistoryExtractor",
        )

        resident = resolver.resident_repository.get_by_name("Resident")
        assert resident is not None
        assert resident.date_of_birth == date(1946, 2, 1)
        assert resident.sex == "f"
        assert resident.height_in == 64.5  # noqa: PLR2004


def test_transformer_keeps_stay_optional_and_assigns_lab_when_stay_is_created(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    path = tmp_path / "labs.pdf"
    path.write_bytes(b"first lab report")

    with Session(engine) as session:
        resolver = ResidentResolver(
            resident_repository=ResidentRepo(session),
            facility_repository=FacilityRepo(session),
            stay_repository=ResidentFacilityStayRepo(session),
        )
        transformed = ExtractedFactTransformer(resolver).transform(
            path,
            [
                ExtractedFactCreate(
                    facility_name="Sunrise Care",
                    facility_resident_identifier="RES-1",
                    resident_name="Jane Doe",
                    payload=LabPayload(
                        name="Albumin",
                        result="3.2",
                        observed_at=_OBSERVED_AT,
                    ),
                    confidence=1.0,
                ),
            ],
            extractor_name="PccLabResultsExtractor",
        )

        fact = transformed.extracted_facts[0]
        lab = typing.cast("ResidentLab", transformed.related_models[0])
        facility = resolver.facility_repository.get_by_name("Sunrise Care")
        resident = resolver.resident_repository.get_by_name("Jane Doe")

        assert facility is not None
        assert resident is not None
        assert resident.id is not None
        assert fact.resident_id == resident.id
        assert fact.facility_id == facility.id
        assert fact.resident_facility_stay_id is None
        assert lab.resident_facility_stay_id is None
        assert resolver.stay_repository.get_by_resident_id(resident.id) == []

        resolver.resident_repository.load_transformed_documents([transformed])
        resolution = resolver.resolve_or_create(
            facility_name="Sunrise Care",
            facility_resident_identifier="RES-1",
            resident_name="Jane Doe",
            effective_at=_OBSERVED_AT,
        )

        assert resolution.resident_facility_stay_id is not None
        assert fact.resident_facility_stay_id == resolution.resident_facility_stay_id
        assert lab.resident_facility_stay_id == resolution.resident_facility_stay_id
        stay = resolver.stay_repository.get_by_id(
            resolution.resident_facility_stay_id,
        )
        assert stay is not None
        assert stay.facility_resident_identifier == "RES-1"
        assert stay.admitted_at is not None
        assert stay.admitted_at.replace(tzinfo=UTC) == _OBSERVED_AT

        second_path = tmp_path / "labs-with-stay.pdf"
        second_path.write_bytes(b"lab report with explicit stay")
        with_stay = ExtractedFactTransformer(resolver).transform(
            second_path,
            [
                ExtractedFactCreate(
                    resident_facility_stay_id=resolution.resident_facility_stay_id,
                    payload=LabPayload(
                        name="Hemoglobin",
                        result="12.0",
                        observed_at=_OBSERVED_AT,
                    ),
                    confidence=1.0,
                ),
            ],
            extractor_name="PccLabResultsExtractor",
        )
        assert with_stay.extracted_facts[0].resident_id == resident.id
        assert with_stay.extracted_facts[0].facility_id == facility.id
        assert (
            with_stay.extracted_facts[0].resident_facility_stay_id
            == resolution.resident_facility_stay_id
        )


def test_transformer_keeps_identical_payloads_for_different_residents(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "shared.csv"
    path.write_text("shared report", encoding="utf-8")
    resident_ids = {"RES1": 7, "RES2": 8}
    facts = [
        ExtractedFactCreate(
            facility_resident_identifier=identifier,
            payload=MealIntakePayload(
                min_percent=75,
                max_percent=75,
                observed_at=_OBSERVED_AT,
            ),
            confidence=1.0,
        )
        for identifier in resident_ids
    ]

    transformed = ExtractedFactTransformer(stub_resolver(resident_ids)).transform(
        path,
        facts,
        extractor_name="UnknownDocument",
    )

    assert len(transformed.document_sources) == 2  # noqa: PLR2004
    assert len(transformed.extracted_facts) == 2  # noqa: PLR2004
    assert {fact.resident_id for fact in transformed.extracted_facts} == set(
        resident_ids.values(),
    )


def test_transformer_requires_resident_identity(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("resident report", encoding="utf-8")
    fact = ExtractedFactCreate(
        payload=EdemaPayload(location="Lower extremities", observed_at=_OBSERVED_AT),
        confidence=1.0,
    )

    with pytest.raises(ValueError, match="facility_resident_identifier is required"):
        ExtractedFactTransformer(stub_resolver({})).transform(
            path,
            [fact],
            extractor_name="UnknownDocument",
        )


def test_transformer_converts_order_date_to_fact_datetime(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "orders.pdf"
    path.write_bytes(b"orders")
    fact = ExtractedFactCreate(
        facility_resident_identifier="RES1",
        payload=OrderPayload(
            summary="Renal diet",
            revision_date=date(2026, 8, 27),
        ),
        confidence=1.0,
    )

    transformed = ExtractedFactTransformer(stub_resolver({"RES1": 7})).transform(
        path,
        [fact],
        extractor_name="PccOrderReportExtractor",
    )

    assert transformed.extracted_facts[0].effective_at == datetime(
        2026,
        8,
        27,
        tzinfo=UTC,
    )
