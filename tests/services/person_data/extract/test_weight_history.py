from __future__ import annotations

import asyncio
import typing

import pymupdf
import pytest

from ntk.models.extracted_fact_create import WeightPayload
from ntk.pipelines.person.ingestion.extract.pcc_weight_history import (
    PccWeightHistoryExtractor,
)

if typing.TYPE_CHECKING:
    import pathlib


def _insert_lines(page: pymupdf.Page, lines: list[str]) -> None:
    for index, line in enumerate(lines):
        page.insert_text((20, 40 + (index * 18)), line, fontsize=8)


def test_all_persons_weight_state_continues_across_pages(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "all-person-weights.pdf"
    with pymupdf.open() as document:
        first_page = document.new_page(width=900, height=700)
        _insert_lines(
            first_page,
            [
                "Weights and Vitals Summary",
                "Facility",
                "Resident: All",
                "Vital: Height, Weight",
                "Akhtar, Naseem (EN140427) Location: 3B-LTC 366 A, Height: 63 Inches",
                "Weight Summary",
                "08/22/2026 22:21 84 Lbs (Mechanical Lift)",
            ],
        )
        second_page = document.new_page(width=900, height=700)
        _insert_lines(
            second_page,
            [
                "05/11/2026 10:14 94 Lbs (Wheelchair)",
                "04/24/2026 08:30 100 Lbs (Wheelchair)",
                "ANDERSON, BARBARA H (190372) Location: 2A, Height: 65 Inches",
                "Height Summary",
                "08/01/2026 08:00 65 Inches (Standing)",
                "Weight Summary",
                "08/20/2026 09:00 130 Lbs (Standing)",
            ],
        )
        document.save(path)

    facts = asyncio.run(PccWeightHistoryExtractor(path).extract())
    weight_payloads = [
        fact.payload for fact in facts if isinstance(fact.payload, WeightPayload)
    ]

    assert len(weight_payloads) == len(facts)
    assert [fact.source_person_identifier for fact in facts] == [
        "EN140427",
        "EN140427",
        "EN140427",
        "190372",
    ]
    assert [payload.weight_lb for payload in weight_payloads] == [84, 94, 100, 130]
    assert [fact.source_page for fact in facts] == [1, 2, 2, 2]
    assert facts[1].source_person_name == "Akhtar, Naseem"
    assert facts[-1].source_person_name == "ANDERSON, BARBARA H"


def test_person_header_at_page_end_applies_on_following_page(
    tmp_path: pathlib.Path,
) -> None:
    expected_height = 70
    path = tmp_path / "person-header-continuation.pdf"
    with pymupdf.open() as document:
        first_page = document.new_page(width=900, height=700)
        _insert_lines(
            first_page,
            [
                "Weights and Vitals Summary",
                "Facility",
                "Resident: All",
                "Vital: Height, Weight",
                "AIG, ABRAHAM (06785) Location: 4A, Height: 70 Inches",
            ],
        )
        second_page = document.new_page(width=900, height=700)
        _insert_lines(
            second_page,
            [
                "Weight Summary",
                "08/03/2026 07:57 240.9 Lbs (Standing)",
            ],
        )
        document.save(path)

    facts = asyncio.run(PccWeightHistoryExtractor(path).extract())

    assert len(facts) == 1
    assert facts[0].source_person_identifier == "06785"
    assert facts[0].source_person_name == "AIG, ABRAHAM"
    assert facts[0].height_in == expected_height
    assert facts[0].source_page == 2  # noqa: PLR2004


def test_weight_rows_deduplicate_by_person_and_measurement_time(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "duplicate-weights.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=900, height=700)
        _insert_lines(
            page,
            [
                "Weights and Vitals Summary",
                "Facility",
                "Resident: Person One (R1)",
                "Weight Summary",
                "08/24/2026 22:17 120 Lbs (Wheelchair)",
                "08/24/2026 22:17 121 Lbs (Standing)",
            ],
        )
        document.save(path)

    facts = asyncio.run(PccWeightHistoryExtractor(path).extract())

    assert len(facts) == 1
    assert facts[0].source_person_identifier == "R1"
    assert isinstance(facts[0].payload, WeightPayload)
    assert facts[0].payload.weight_lb == 120  # noqa: PLR2004


def test_demo_extracts_single_person_weights_without_identity(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "deidentified-weights.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        _insert_lines(
            page,
            [
                "Weights and Vitals Summary",
                "Facility",
                "Resident:",
                "Height: 72 Inches",
                "Weight Summary",
                "08/24/2026 22:17 120 Lbs (Wheelchair)",
            ],
        )
        document.save(path)

    extractor = PccWeightHistoryExtractor(path)
    with pytest.raises(ValueError, match="Unable to determine the person"):
        asyncio.run(extractor.extract())

    facts = asyncio.run(extractor.extract_for_demo())

    assert len(facts) == 1
    assert facts[0].source_person_identifier is None
    assert facts[0].source_person_name is None
    assert isinstance(facts[0].payload, WeightPayload)
    assert facts[0].payload.weight_lb == 120  # noqa: PLR2004
