from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime
from types import SimpleNamespace

from ntk.agents.resident_data_agent import (
    ResidentDataAgent,
    ResidentDataDependencies,
)
from ntk.models.sql.resident import (
    CsvWoundReportExtraction,
    PccOrder,
    PccOrderReportExtraction,
    PccProgressNotesExtraction,
    ResidentContext,
    SourceReference,
    Wound,
)

if typing.TYPE_CHECKING:
    import pathlib


def _source(name: str) -> SourceReference:
    return SourceReference(
        source_type="test",
        source=name,
        extracted_at=datetime(2026, 8, 24, tzinfo=UTC),
    )


class FakeExtractorService:
    def __init__(self) -> None:
        self.calls: list[tuple[pathlib.Path, str | None]] = []

    @staticmethod
    def get_extractor(path: pathlib.Path) -> object | None:
        if "progress" in path.name:
            return type("PccProgressNotesExtractor", (), {})()
        if "orders" in path.name:
            return type("PccOrderReportExtractor", (), {})()
        return None

    def extract_file(
        self,
        path: pathlib.Path,
        *,
        expected_extractor: str | None = None,
    ) -> object:
        self.calls.append((path, expected_extractor))
        if expected_extractor == "PccProgressNotesExtractor":
            return PccProgressNotesExtraction(
                facility_id="EN140175",
                diagnoses=["ESRD"],
                source=_source(path.name),
            )
        return PccOrderReportExtraction(
            facility_id="EN140175",
            orders=[PccOrder(summary="Renal diet")],
            source=_source(path.name),
        )


class FakeAgent:
    def __init__(self) -> None:
        self.called = False
        self.prompt = ""
        self.dependencies: ResidentDataDependencies | None = None

    async def run(
        self,
        prompt: str,
        *,
        deps: ResidentDataDependencies,
    ) -> object:
        self.called = True
        self.prompt = prompt
        self.dependencies = deps
        return SimpleNamespace(
            output=ResidentContext(facility_id="LLM-CONFLICT", diet="Renal"),
        )


class FakeResidentRepo:
    @staticmethod
    def get_by_facility_id(_facility_id: str) -> None:
        return None


class MultiResidentWoundService:
    def __init__(self) -> None:
        self.calls: list[tuple[pathlib.Path, str | None, str | None]] = []

    @staticmethod
    def get_extractor(path: pathlib.Path) -> object:
        extractor_name = (
            "WoundReportExtractor"
            if "wounds" in path.name
            else "PccOrderReportExtractor"
        )
        return type(extractor_name, (), {})()

    def extract_file(
        self,
        path: pathlib.Path,
        *,
        expected_extractor: str | None = None,
        resident_facility_id: str | None = None,
    ) -> object:
        self.calls.append((path, expected_extractor, resident_facility_id))
        if expected_extractor == "PccOrderReportExtractor":
            return PccOrderReportExtraction(
                facility_id="EN140175",
                orders=[PccOrder(summary="Renal diet")],
                source=_source(path.name),
            )
        assert resident_facility_id == "EN140175"
        return CsvWoundReportExtraction(
            facility_id=resident_facility_id,
            wounds=[Wound(type="Pressure Injury", location="Sacrum")],
            source=_source(path.name),
        )


def test_run_reviews_progress_notes_after_deterministic_merge(
    tmp_path: pathlib.Path,
) -> None:
    progress_path = tmp_path / "progress.pdf"
    order_path = tmp_path / "orders.pdf"
    unknown_path = tmp_path / "resident.csv"
    progress_path.write_bytes(b"pdf")
    order_path.write_bytes(b"pdf")
    unknown_path.write_text("custom,value\nmeal intake,75%")
    service = FakeExtractorService()
    agent = FakeAgent()
    runner = ResidentDataAgent(
        agent=agent,  # ty: ignore[invalid-argument-type]
        extractor_service=service,  # ty: ignore[invalid-argument-type]
        resident_repo=FakeResidentRepo(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(runner.run([progress_path, order_path, unknown_path]))

    assert agent.called is True
    assert "progress.pdf" in agent.prompt
    assert "resident.csv" in agent.prompt
    assert result.facility_id == "EN140175"
    assert result.diagnoses == ["ESRD"]
    assert result.orders == [PccOrder(summary="Renal diet")]
    assert result.diet == "Renal"
    assert {conflict.field for conflict in result.conflicts} == {"facility_id"}
    assert service.calls == [
        (progress_path, "PccProgressNotesExtractor"),
        (order_path, "PccOrderReportExtractor"),
    ]
    assert agent.dependencies is not None
    assert agent.dependencies.unprocessed_file_ids == {"file_1", "file_3"}


def test_run_skips_agent_when_deterministic_extraction_is_complete(
    tmp_path: pathlib.Path,
) -> None:
    order_path = tmp_path / "orders.pdf"
    order_path.write_bytes(b"pdf")
    service = FakeExtractorService()
    agent = FakeAgent()
    runner = ResidentDataAgent(
        agent=agent,  # ty: ignore[invalid-argument-type]
        extractor_service=service,  # ty: ignore[invalid-argument-type]
        resident_repo=FakeResidentRepo(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(runner.run([order_path]))

    assert agent.called is False
    assert result.facility_id == "EN140175"
    assert result.orders == [PccOrder(summary="Renal diet")]
    assert service.calls == [(order_path, "PccOrderReportExtractor")]


def test_run_selects_current_resident_from_multi_resident_wound_report(
    tmp_path: pathlib.Path,
) -> None:
    wound_path = tmp_path / "wounds.csv"
    order_path = tmp_path / "orders.pdf"
    wound_path.write_text("wounds")
    order_path.write_bytes(b"pdf")
    service = MultiResidentWoundService()
    agent = FakeAgent()
    runner = ResidentDataAgent(
        agent=agent,  # ty: ignore[invalid-argument-type]
        extractor_service=service,  # ty: ignore[invalid-argument-type]
        resident_repo=FakeResidentRepo(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(runner.run([wound_path, order_path]))

    assert agent.called is False
    assert result.facility_id == "EN140175"
    assert result.wounds == [Wound(type="Pressure Injury", location="Sacrum")]
    assert service.calls == [
        (order_path, "PccOrderReportExtractor", None),
        (wound_path, "WoundReportExtractor", "EN140175"),
    ]
