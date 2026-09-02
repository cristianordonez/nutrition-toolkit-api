from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntk.agents.data_extraction_agent import (
    DataExtractionAgent,
    ExtractedClinicalFacts,
    ExtractionInput,
    UnknownDocumentExtractionResult,
)
from ntk.models.ai_extraction import (
    AIExtractedClinicalFact,
    AIExtractedFact,
    AIExtractedIdentity,
    AIUnknownDocumentFact,
)
from ntk.models.extracted_fact_create import (
    ClinicalFactPayload,
    MealIntakePayload,
    WeightPayload,
)


class FakeAgent:
    def __init__(self, result: ExtractedClinicalFacts) -> None:
        self.result = result
        self.prompts: list[str] = []

    async def run(self, prompt: str) -> object:
        self.prompts.append(prompt)
        return SimpleNamespace(output=self.result)


class FakeUnknownDocumentAgent:
    def __init__(self, result: UnknownDocumentExtractionResult) -> None:
        self.result = result
        self.prompts: list[str] = []

    async def run(self, prompt: str) -> object:
        self.prompts.append(prompt)
        return SimpleNamespace(output=self.result)


def test_run_returns_extracted_clinical_facts() -> None:
    fact = AIExtractedClinicalFact(
        payload=MealIntakePayload(
            min_percent=50,
            max_percent=75,
            appetite="fair",
            observed_at=datetime(2026, 8, 20, tzinfo=UTC),
        ),
        confidence=0.9,
    )
    expected = ExtractedClinicalFacts(facts=[fact])
    fake = FakeAgent(expected)
    agent = DataExtractionAgent(
        fact_agent=fake,  # ty: ignore[invalid-argument-type]
    )
    extraction_input = ExtractionInput(
        text="Meal intake was 50-75% with fair appetite.",
        document_filename="note.txt",
    )

    result = asyncio.run(agent.run(extraction_input))

    assert result == expected
    assert fake.prompts == [extraction_input.model_dump_json()]


def test_run_returns_empty_facts_without_calling_model_for_blank_text() -> None:
    fake = FakeAgent(ExtractedClinicalFacts())
    agent = DataExtractionAgent(
        fact_agent=fake,  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(agent.run(ExtractionInput(text="  \n")))

    assert result == ExtractedClinicalFacts()
    assert fake.prompts == []


def test_agent_output_schema_excludes_deterministic_first_payloads() -> None:
    schema = str(ExtractedClinicalFacts.model_json_schema())

    assert "OrderPayload" not in schema
    assert "WeightPayload" not in schema
    assert "LabPayload" not in schema
    assert "WoundPayload" in schema
    assert "KnowledgeChunkPayload" not in schema
    assert "DialysisPayload" not in schema


def test_dialysis_is_returned_as_a_clinical_fact() -> None:
    observed_at = datetime(2026, 8, 20, tzinfo=UTC)

    result = ExtractedClinicalFacts.model_validate(
        {
            "facts": [
                {
                    "payload": {
                        "type": "clinical_fact",
                        "clinical_fact_type": "observation",
                        "observation_type": "dialysis",
                        "description": "Hemodialysis on Monday, Wednesday, Friday.",
                        "observed_at": observed_at,
                    },
                    "confidence": 1,
                },
            ],
        },
    )

    assert isinstance(result.facts[0].payload, ClinicalFactPayload)
    assert result.facts[0].payload.observation_type == "dialysis"


def test_run_serializes_all_extraction_input_metadata() -> None:
    fake = FakeAgent(ExtractedClinicalFacts())
    agent = DataExtractionAgent(
        fact_agent=fake,  # ty: ignore[invalid-argument-type]
    )
    note_date = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)
    extraction_input = ExtractionInput(
        text="Resident consumed 75% of lunch.",
        document_filename="progress-notes.pdf",
        note_date=note_date,
    )

    asyncio.run(agent.run(extraction_input))

    assert json.loads(fake.prompts[0]) == {
        "text": extraction_input.text,
        "document_filename": "progress-notes.pdf",
        "note_date": note_date.isoformat().replace("+00:00", "Z"),
    }


def test_run_unknown_document_returns_identity_bound_facts() -> None:
    fact = AIUnknownDocumentFact(
        identity=AIExtractedIdentity(
            resident_name="Patel, Sushilaben",
            facility_resident_identifier="EN140519",
            facility_name="Embassy Manor at Edison",
        ),
        fact=AIExtractedFact(
            payload=WeightPayload(
                weight_lb=138,
                measured_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
            confidence=0.98,
        ),
    )
    fake = FakeUnknownDocumentAgent(
        UnknownDocumentExtractionResult(facts=[fact]),
    )
    extraction_input = ExtractionInput(
        text="Resident Name: Patel, Sushilaben (EN140519); weight 138 lb",
        document_filename="unknown.pdf",
    )

    result = asyncio.run(
        DataExtractionAgent(
            unknown_document_agent=fake,  # ty: ignore[invalid-argument-type]
        ).run_unknown_document(extraction_input),
    )

    assert result == [fact]
    assert fake.prompts == [extraction_input.model_dump_json()]


def test_run_unknown_document_skips_model_for_blank_text() -> None:
    fake = FakeUnknownDocumentAgent(UnknownDocumentExtractionResult())

    result = asyncio.run(
        DataExtractionAgent(
            unknown_document_agent=fake,  # ty: ignore[invalid-argument-type]
        ).run_unknown_document(ExtractionInput(text=" \n\t ")),
    )

    assert result == []
    assert fake.prompts == []


def test_data_extraction_agent_propagates_provider_errors() -> None:
    class FailingAgent:
        @staticmethod
        async def run(_prompt: str) -> object:
            message = "provider unavailable"
            raise ConnectionError(message)

    agent = DataExtractionAgent(
        fact_agent=FailingAgent(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(ConnectionError, match="provider unavailable"):
        asyncio.run(agent.run(ExtractionInput(text="Clinical note")))


def test_extraction_result_fact_lists_are_not_shared() -> None:
    first = ExtractedClinicalFacts()
    second = ExtractedClinicalFacts()

    first.facts.append(
        AIExtractedClinicalFact(
            payload=MealIntakePayload(
                min_percent=50,
                observed_at=datetime(2026, 9, 2, tzinfo=UTC),
            ),
            confidence=1,
        ),
    )

    assert second.facts == []
