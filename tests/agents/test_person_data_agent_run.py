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
    AppetitePayload,
    DialysisPayload,
    MealIntakePayload,
    WeightPayload,
)
from ntk.models.sql.clinical import AppetiteLevel, ClinicalStatus, DialysisType


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
    observed_at = datetime(2026, 8, 20, tzinfo=UTC)
    facts = [
        AIExtractedClinicalFact(
            payload=MealIntakePayload(
                min_percent=50,
                max_percent=75,
                observed_at=observed_at,
            ),
            confidence=0.9,
        ),
        AIExtractedClinicalFact(
            payload=AppetitePayload(
                appetite=AppetiteLevel.FAIR,
                observed_at=observed_at,
            ),
            confidence=0.9,
        ),
    ]
    expected = ExtractedClinicalFacts(facts=facts)
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


def test_agent_output_schema_uses_semantic_clinical_payloads() -> None:
    definitions = ExtractedClinicalFacts.model_json_schema()["$defs"]

    assert "WeightPayload" not in definitions
    assert "LabPayload" not in definitions
    assert "KnowledgeChunkPayload" not in definitions
    assert "MedicationPayload" not in definitions
    assert "DietPayload" not in definitions
    assert "EnteralFeedingPayload" not in definitions
    assert "DialysisPayload" in definitions
    assert "OralFeedingStatusPayload" in definitions
    assert "FoodPreferencePayload" in definitions
    assert "NutritionGoalPayload" in definitions


def test_dialysis_is_returned_as_a_semantic_domain_fact() -> None:
    observed_at = datetime(2026, 8, 20, tzinfo=UTC)

    result = ExtractedClinicalFacts.model_validate(
        {
            "facts": [
                {
                    "payload": {
                        "type": "dialysis",
                        "dialysis_type": "hemodialysis",
                        "schedule": "M/W/F",
                        "status": "active",
                        "observed_at": observed_at,
                    },
                    "confidence": 1,
                },
            ],
        },
    )

    payload = result.facts[0].payload
    assert isinstance(payload, DialysisPayload)
    assert payload.dialysis_type is DialysisType.HEMODIALYSIS
    assert payload.schedule == "M/W/F"
    assert payload.status is ClinicalStatus.ACTIVE


def test_run_serializes_all_extraction_input_metadata() -> None:
    fake = FakeAgent(ExtractedClinicalFacts())
    agent = DataExtractionAgent(
        fact_agent=fake,  # ty: ignore[invalid-argument-type]
    )
    note_date = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)
    extraction_input = ExtractionInput(
        text="Person consumed 75% of lunch.",
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
            source_person_name="Patel, Sushilaben",
            source_person_identifier="EN140519",
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
        text="Person Name: Patel, Sushilaben (EN140519); weight 138 lb",
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
