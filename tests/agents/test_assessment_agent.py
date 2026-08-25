from __future__ import annotations

import asyncio
import json
import pathlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ntk.agents.assessment_agent import AdmissionAgent
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.resident import ResidentContext

RESIDENT_AGE = 80


class FakeAgent:
    def __init__(self, output: str) -> None:
        self.output = output
        self.prompt = ""

    async def run(self, prompt: str) -> object:
        self.prompt = prompt
        return SimpleNamespace(output=self.output)


def _match(filename: str, text: str) -> RagSearchMatch:
    return RagSearchMatch(
        document_id=uuid4(),
        filename=filename,
        chunk_text=text,
        similarity=0.9,
    )


def test_admission_agent_passes_explicit_input_contract() -> None:
    fake = FakeAgent("  Nutrition Readmission Assessment  ")
    agent = AdmissionAgent(agent=fake)  # ty: ignore[invalid-argument-type]
    resident = ResidentContext(age=RESIDENT_AGE)
    knowledge = [_match("manual.pdf", "clinical guidance")]
    previous = [_match("assessment.pdf", "style example")]
    assessment = asyncio.run(
        agent.generate(resident, knowledge, previous, "wound healing"),
    )
    payload = json.loads(fake.prompt)
    assert payload["resident_data"]["age"] == RESIDENT_AGE
    assert payload["resident_data"]["progress_notes"] == []
    assert "resident_id" not in payload["resident_data"]
    assert payload["retrieved_knowledge"][0]["chunk_text"] == "clinical guidance"
    assert payload["previous_assessments"][0]["chunk_text"] == "style example"
    assert payload["request_focus"] == "wound healing"
    assert assessment.content == "Nutrition Readmission Assessment"
    assert assessment.source.value == "generated"
    assert assessment.source_filename is None
    assert assessment.to_console() == assessment.content


def test_admission_agent_rejects_empty_note() -> None:
    agent = AdmissionAgent(agent=FakeAgent("  "))  # ty: ignore[invalid-argument-type]
    with pytest.raises(RuntimeError, match="empty note"):
        asyncio.run(
            agent.generate(
                ResidentContext(),
                [],
                [],
            ),
        )


def test_assessment_prompt_defines_inputs_and_style() -> None:
    prompt = (pathlib.Path(__file__).parents[2] / "src/ntk/static/prompt.md").read_text(
        encoding="utf-8",
    )

    assert "## Inputs and evidence" in prompt
    assert "`resident_data`" in prompt
    assert "`comparison`" in prompt
    assert "`retrieved_knowledge`" in prompt
    assert "`previous_assessments`" in prompt
    assert "## Style" in prompt
    assert "## Final validation" in prompt
    assert "Do not add a `Care Coordination:` section" in prompt
    assert "(current - prior) / prior x 100" in prompt
    assert "Do not present an old diet" in prompt
    assert "wound status is unknown" in prompt
    assert "include dose, route, frequency" in prompt
    assert "grouped by indication" in prompt
    assert "include only nutrition-relevant results" in prompt
    assert "every abnormal value" in prompt
    assert "briefly interpret each abnormal result" in prompt
