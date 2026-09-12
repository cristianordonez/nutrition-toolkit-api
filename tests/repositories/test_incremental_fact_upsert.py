from __future__ import annotations

import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.extracted_fact_create import (
    AllergyPayload,
    DietPayload,
    EdemaPayload,
    ExtractedFactCreate,
    FactPayload,
    LabPayload,
)
from ntk.models.sql.clinical import PersonAllergy, PersonDiet, PersonEdema, PersonLab
from ntk.models.sql.clinical.common import ClinicalStatus
from ntk.pipelines.person.ingestion.transformer import ExtractedFactTransformer
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib

_OBSERVED_AT = datetime(2026, 8, 24, 22, 17, tzinfo=UTC)


@pytest.mark.parametrize(
    ("first_payload", "second_payload", "model", "field_name", "expected"),
    [
        (
            LabPayload(name="Albumin", result="3.0", observed_at=_OBSERVED_AT),
            LabPayload(name="Albumin", result="3.2", observed_at=_OBSERVED_AT),
            PersonLab,
            "result",
            "3.2",
        ),
        (
            DietPayload(
                diet_type="Renal",
                status=ClinicalStatus.ACTIVE,
                observed_at=_OBSERVED_AT,
            ),
            DietPayload(
                diet_type="Renal",
                status=ClinicalStatus.INACTIVE,
                observed_at=_OBSERVED_AT,
            ),
            PersonDiet,
            "status",
            ClinicalStatus.INACTIVE,
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
            PersonEdema,
            "severity",
            "2+",
        ),
    ],
)
def test_constrained_incremental_fact_is_upserted(  # noqa: PLR0913
    *,
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
        repository = PersonRepo(session)
        facility_repository = FacilityRepo(session)
        resolver = FacilityResolver(facility_repository)
        resolver.register_trusted(name="Facility")
        transformer = ExtractedFactTransformer(
            PersonService(
                repository,
                resolver,
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
        source_person_identifier="R-1",
        source_person_name="Person",
        facility_name="Facility",
        payload=payload,
        confidence=1,
    )


def test_equivalent_diet_formatting_does_not_create_two_active_rows(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    order_path = tmp_path / "orders.pdf"
    note_path = tmp_path / "notes.pdf"
    order_path.write_bytes(b"authoritative order")
    note_path.write_bytes(b"older progress note")
    order_time = datetime(2026, 8, 27, tzinfo=UTC)
    note_time = datetime(2026, 8, 5, tzinfo=UTC)

    with Session(engine) as session:
        repository = PersonRepo(session)
        resolver = FacilityResolver(FacilityRepo(session))
        resolver.register_trusted(name="Facility")
        transformer = ExtractedFactTransformer(PersonService(repository, resolver))
        order = transformer.transform(
            order_path,
            [
                _fact(
                    DietPayload(
                        diet_type="regular",
                        texture="mechanical_soft",
                        liquid_consistency="thin",
                        status=ClinicalStatus.ACTIVE,
                        observed_at=order_time,
                    ),
                ),
            ],
            extractor_name="PccOrderReportExtractor",
        )
        note = transformer.transform(
            note_path,
            [
                _fact(
                    DietPayload(
                        diet_type="Regular Diet",
                        texture="mechanical soft",
                        liquid_consistency="thin",
                        status=ClinicalStatus.ACTIVE,
                        observed_at=note_time,
                    ),
                ),
            ],
            extractor_name="PccProgressNotesExtractor",
        )

        repository.load_transformed_documents([order])
        repository.load_transformed_documents([note])

        diets = list(session.exec(select(PersonDiet)).all())
        assert len(diets) == 1
        assert diets[0].texture == "mechanical_soft"
        assert diets[0].observed_at == order_time.replace(tzinfo=None)


def test_newer_allergy_reconciliation_keeps_required_provenance_fk(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    first_path = tmp_path / "first-allergy.pdf"
    second_path = tmp_path / "second-allergy.pdf"
    first_path.write_bytes(b"first allergy report")
    second_path.write_bytes(b"second allergy report")
    first_time = datetime(2026, 1, 1, tzinfo=UTC)
    second_time = datetime(2026, 1, 29, tzinfo=UTC)

    with Session(engine) as session:
        repository = PersonRepo(session)
        resolver = FacilityResolver(FacilityRepo(session))
        resolver.register_trusted(name="Facility")
        transformer = ExtractedFactTransformer(PersonService(repository, resolver))
        first = transformer.transform(
            first_path,
            [
                _fact(
                    AllergyPayload(
                        no_known_allergies=True,
                        observed_at=first_time,
                    ),
                ),
            ],
            extractor_name="AllergyExtractor",
        )
        repository.load_transformed_documents([first])
        first_allergy = session.exec(select(PersonAllergy)).one()
        first_fact_id = first_allergy.extracted_fact_id

        second = transformer.transform(
            second_path,
            [
                _fact(
                    AllergyPayload(
                        no_known_allergies=True,
                        observed_at=second_time,
                    ),
                ),
                # A following constrained record invokes the lookup query that
                # previously autoflushed the allergy with a null provenance ID.
                _fact(
                    DietPayload(
                        diet_type="regular",
                        status=ClinicalStatus.ACTIVE,
                        observed_at=second_time,
                    ),
                ),
            ],
            extractor_name="AllergyExtractor",
        )
        repository.load_transformed_documents([second])

        allergy = session.exec(select(PersonAllergy)).one()
        assert allergy.observed_at == second_time.replace(tzinfo=None)
        assert allergy.extracted_fact_id is not None
        assert allergy.extracted_fact_id != first_fact_id
