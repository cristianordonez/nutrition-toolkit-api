from __future__ import annotations

import asyncio
import typing

import pymupdf
from sqlmodel import Session, SQLModel, create_engine, select

from engine.models.sql.clinical import PersonWeight
from engine.models.sql.facility import Facility
from engine.pipelines.ncp.create.context_budgeter import ContextBudgeter
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.repositories.clinical_note_repo import ClinicalNoteRepo
from engine.repositories.facility_repo import FacilityRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.facility_resolver import FacilityResolver
from engine.services.person.detail_builder import PersonDetailBuilder
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib

EXPECTED_WEIGHT = 142


def test_ingestion_builds_a_generation_request_from_persisted_data(
    tmp_path: pathlib.Path,
) -> None:
    db_engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(db_engine)
    pdf = _weight_report(tmp_path)

    with Session(db_engine, expire_on_commit=False) as session:
        FacilityRepo(session).create(
            Facility(facility_identifier="FAC-1", name="Sunrise Care"),
        )
        facility_resolver = FacilityResolver(FacilityRepo(session))
        person_service = PersonService(PersonRepo(session), facility_resolver)
        pipeline = PersonIngestionPipeline(
            clinical_note_repository=ClinicalNoteRepo(session),
            person_service=person_service,
            facility_resolver=facility_resolver,
        )

        result = asyncio.run(pipeline.ingest(files=[pdf]))

        assert len(result.documents) == 1
        stored_weight = session.exec(select(PersonWeight)).one()
        assert stored_weight.weight_lb == EXPECTED_WEIGHT

    with Session(db_engine, expire_on_commit=False) as session:
        person = PersonRepo(session).get_by_identifier("R1")
        assert person is not None
        records = PersonRepo(session).get_clinical_records(person.id)
        detail = PersonDetailBuilder().build(person, records)

        budget_result = ContextBudgeter().budget(
            detail,
            facility_identifier="FAC-1",
            additional_context="annual nutrition review",
        )

    request = budget_result.request
    assert request.person_identifier == "R1"
    assert request.facility_identifier == "FAC-1"
    assert request.additional_context == "annual nutrition review"
    assert request.person.name == "Person One"
    assert len(request.person.weight_history) == 1
    assert request.person.weight_history[0].weight_lb == EXPECTED_WEIGHT
    assert request.person.weight_history[0].description == "Standing"


def _weight_report(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "weights.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=900, height=700)
        for index, line in enumerate(
            (
                "Weights and Vitals Summary",
                "Sunrise Care",
                "Resident: Person One (R1)",
                "Vital: Height, Weight",
                "Weight Summary",
                "08/24/2026 22:17 142 Lbs (Standing)",
            ),
        ):
            page.insert_text((20, 40 + (index * 18)), line, fontsize=8)
        document.save(path)
    return path
