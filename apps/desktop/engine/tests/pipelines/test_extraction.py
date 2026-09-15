"""Tests for the person extractor contract built on the shared base."""

from __future__ import annotations

from datetime import UTC, datetime

from engine.models.extracted_fact_create import ExtractedFactCreate, WeightPayload
from engine.pipelines.person.ingestion.extract.base import PersonExtractor
from ntk.pipelines.extraction import DocumentExtractor


class FactExtractor(PersonExtractor):
    """Concrete person extractor used to exercise fact construction."""

    def is_expected_format(self) -> bool:
        return True

    async def extract(self) -> list[ExtractedFactCreate]:
        return []


def test_person_extractor_is_a_document_extractor() -> None:
    assert issubclass(PersonExtractor, DocumentExtractor)


def test_person_extractor_builds_facts_and_parses_facility(
    tmp_path,  # noqa: ANN001
) -> None:
    extractor = FactExtractor(tmp_path / "weights.pdf")
    fact = extractor._build_extracted_fact(  # noqa: SLF001
        WeightPayload(
            weight_lb=150,
            measured_at=datetime(2026, 9, 1, tzinfo=UTC),
        ),
        source_person_identifier="A123",
        facility_name="Embassy Manor",
    )

    assert fact.source_person_identifier == "A123"
    assert fact.facility_name == "Embassy Manor"
    assert fact.confidence == 1.0
    assert (
        PersonExtractor._parse_facility_name(  # noqa: SLF001
            "Weights and Vitals Summary\nEmbassy Manor\nResident: Example",
            "Weights and Vitals Summary",
        )
        == "Embassy Manor"
    )
    assert not hasattr(DocumentExtractor, "_parse_facility_name")
