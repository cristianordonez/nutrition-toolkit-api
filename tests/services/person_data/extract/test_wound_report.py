from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.models.extracted_fact_create import ExtractedFactCreate, WoundPayload
from ntk.models.sql.person import PersonWound
from ntk.pipelines.person.ingestion.extract.wound_report import WoundReportExtractor
from ntk.pipelines.person.ingestion.transformer import ExtractedFactTransformer
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib


def test_wound_report_uses_report_end_date_as_observed_at(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "wounds.csv"
    report.write_text(
        "CUSTOM Wound Type Tabular Report - WHA,,,8/25/2026 - 8/26/2026\n"
        "Facility: Embassy Manor\n"
        "Patient Number,Name,Wound Type,Wound Location,Weeks In Treatment\n"
        "EN140468,Chen Naijing,Pressure Injury,Buttock Left,1\n",
        encoding="utf-8",
    )

    facts = asyncio.run(WoundReportExtractor(report).extract())

    assert len(facts) == 1
    assert facts[0].source_person_identifier == "EN140468"
    assert facts[0].source_person_name == "Chen Naijing"
    assert facts[0].facility_name == "Embassy Manor"
    payload = facts[0].payload
    assert isinstance(payload, WoundPayload)
    assert payload.observed_at == datetime(2026, 8, 26, tzinfo=UTC)


def test_wound_report_preserves_observed_facility_name() -> None:
    assert (
        WoundReportExtractor._parse_wound_facility_name(  # noqa: SLF001
            "Facility: Aristacare at Embassy Manor",
        )
        == "Aristacare at Embassy Manor"
    )


def test_wound_report_without_date_is_rejected(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "wounds.csv"
    report.write_text(
        "CUSTOM Wound Type Tabular Report - WHA\n"
        "Patient Number,Wound Type,Wound Location\n"
        "EN140468,Pressure Injury,Buttock Left\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source observation date"):
        asyncio.run(WoundReportExtractor(report).extract())


def test_duplicate_wound_numbers_are_merged_within_report(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "duplicate-wounds.csv"
    report.write_text(
        "CUSTOM Wound Type Tabular Report - WHA,8/26/2026\n"
        "Patient Number,Name,Wnd #,Wound Type,Wound Location,Stage,"
        "Assessment Note,Physician Orders\n"
        ' RES1 ,Person," 16 ",Pressure Injury,Sacrum,3,Improving,"Cleanse"\n'
        "RES1,Person,16,Pressure Injury,Sacrum,3,"
        'Improving with less drainage,"Cleanse and apply dressing"\n'
        "RES1,Person,17,Pressure Injury,Heel,2,Stable,Offload heel\n"
        "RES1,Person,17,Pressure Injury,Heel,2,"
        "Monitor for worsening,\n",
        encoding="utf-8",
    )

    facts = asyncio.run(WoundReportExtractor(report).extract())

    assert len(facts) == 2  # noqa: PLR2004
    wound_payloads = [
        fact.payload for fact in facts if isinstance(fact.payload, WoundPayload)
    ]
    facts_by_number = {payload.wound_number: payload for payload in wound_payloads}
    assert set(facts_by_number) == {"16", "17"}
    assert facts_by_number["16"].assessment_note == "Improving with less drainage"
    assert facts_by_number["16"].physician_orders == "Cleanse and apply dressing"
    assert facts_by_number["17"].assessment_note == ("Stable\nMonitor for worsening")


def test_reimported_wound_observation_updates_existing_row(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    observed_at = datetime(2026, 8, 26, tzinfo=UTC)

    with Session(engine) as session:
        repository = PersonRepo(session)
        facility_repository = FacilityRepo(session)
        FacilityResolver(facility_repository).register_trusted(name="Facility")
        person_service = PersonService(
            repository,
            FacilityResolver(facility_repository),
        )
        documents = []
        for index, note in enumerate(("Stable", "Stable with less drainage")):
            path = tmp_path / f"wounds-{index}.csv"
            path.write_text(f"report {index}", encoding="utf-8")
            documents.append(
                ExtractedFactTransformer(person_service).transform(
                    path,
                    [
                        ExtractedFactCreate(
                            facility_name="Facility",
                            source_person_identifier="RES1",
                            source_person_name="Person",
                            payload=WoundPayload(
                                wound_number="16",
                                wound_type="Pressure Injury",
                                location="Sacrum",
                                assessment_note=note,
                                observed_at=observed_at,
                            ),
                            confidence=1,
                        ),
                    ],
                    extractor_name="WoundReportExtractor",
                ),
            )

        repository.load_transformed_documents([documents[0]])
        repository.load_transformed_documents([documents[1]])

        wounds = list(session.exec(select(PersonWound)).all())
        assert len(wounds) == 1
        assert wounds[0].wound_number == "16"
        assert wounds[0].assessment_note == "Stable with less drainage"
