from __future__ import annotations

import asyncio
import json
import pathlib
import time
from types import SimpleNamespace

import pytest

from ntk.agents import assessment_agent
from ntk.agents.assessment_agent import (
    AssessmentAgent,
    AssessmentGenerationTimeoutError,
)
from ntk.models.rag import RagSearchMatch

RESIDENT_AGE = 80
EXPECTED_NOTE_COUNT = 20


class FakeAgent:
    def __init__(self, output: str) -> None:
        self.output = output
        self.prompt = ""

    async def run(self, prompt: str) -> object:
        self.prompt = prompt
        return SimpleNamespace(output=self.output)


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int, int]] = []

    def search_context(
        self,
        text: str,
        *,
        knowledge_top_k: int,
        assessment_top_k: int,
    ) -> tuple[list[RagSearchMatch], list[RagSearchMatch]]:
        self.queries.append((text, knowledge_top_k, assessment_top_k))
        return (
            [_match("manual.pdf", "clinical guidance")],
            [_match("assessment.pdf", "style example")],
        )


class FakeResidentContext:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {}
        self.summary_contexts: list[str | None] = []

    def llm_payload(self) -> dict[str, object]:
        return self.payload

    def summary(self, context: str | None = None) -> str:
        self.summary_contexts.append(context)
        return json.dumps({"resident": self.payload, "context": context})


def _match(filename: str, text: str) -> RagSearchMatch:
    return RagSearchMatch(
        document_id=1,
        filename=filename,
        chunk_text=text,
        similarity=0.9,
    )


def test_admission_agent_passes_explicit_input_contract() -> None:
    fake = FakeAgent("  Nutrition Readmission Assessment  ")
    embeddings = FakeEmbeddingService()
    agent = AssessmentAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        embedding_service=embeddings,  # ty: ignore[invalid-argument-type]
    )
    resident = FakeResidentContext(
        {"age": RESIDENT_AGE, "progress_notes": []},
    )
    assessment = asyncio.run(
        agent.run(resident, "wound healing"),
    )
    payload = json.loads(fake.prompt)
    assert payload["resident_context"]["age"] == RESIDENT_AGE
    assert payload["resident_context"]["progress_notes"] == []
    assert "resident_id" not in payload["resident_context"]
    assert payload["retrieved_knowledge"][0]["chunk_text"] == "clinical guidance"
    assert payload["previous_assessments"][0]["chunk_text"] == "style example"
    assert payload["optional_context"] == "wound healing"
    assert len(embeddings.queries) == 1
    query, knowledge_top_k, assessment_top_k = embeddings.queries[0]
    assert "wound healing" in query
    assert knowledge_top_k == 3  # noqa: PLR2004
    assert assessment_top_k == 5  # noqa: PLR2004
    assert assessment == "Nutrition Readmission Assessment"


def test_assessment_agent_bounds_large_runtime_payload() -> None:
    fake = FakeAgent("Nutrition Follow Up")
    resident = FakeResidentContext(
        {
            "progress_notes": [
                {"note_text": f"note {index}: intake stable."}
                for index in range(EXPECTED_NOTE_COUNT)
            ],
        },
    )

    asyncio.run(
        AssessmentAgent(
            agent=fake,  # ty: ignore[invalid-argument-type]
            embedding_service=FakeEmbeddingService(),  # ty: ignore[invalid-argument-type]
        ).run(resident, "focus " * 2_000),
    )

    payload = json.loads(fake.prompt)
    notes = payload["resident_context"]["progress_notes"]
    assert len(notes) == EXPECTED_NOTE_COUNT
    assert {note["note_text"] for note in notes} == {
        f"note {index}: intake stable." for index in range(EXPECTED_NOTE_COUNT)
    }
    assert payload["retrieved_knowledge"]
    assert payload["previous_assessments"]
    assert payload["optional_context"].endswith("[truncated]")


def test_admission_agent_rejects_empty_note() -> None:
    agent = AssessmentAgent(
        agent=FakeAgent("  "),  # ty: ignore[invalid-argument-type]
        embedding_service=FakeEmbeddingService(),  # ty: ignore[invalid-argument-type]
    )
    with pytest.raises(RuntimeError, match="empty note"):
        asyncio.run(
            agent.run(
                FakeResidentContext(),
                "",
            ),
        )


def test_assessment_agent_times_out_stalled_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StalledAgent:
        @staticmethod
        async def run(_prompt: str) -> object:
            await asyncio.sleep(1)
            return SimpleNamespace(output="late")

    monkeypatch.setattr(
        assessment_agent,
        "_ASSESSMENT_GENERATION_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(AssessmentGenerationTimeoutError, match="timed out"):
        asyncio.run(
            AssessmentAgent(
                agent=StalledAgent(),  # ty: ignore[invalid-argument-type]
                embedding_service=FakeEmbeddingService(),  # ty: ignore[invalid-argument-type]
            ).run(FakeResidentContext()),
        )


def test_assessment_agent_times_out_stalled_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowEmbeddingService(FakeEmbeddingService):
        def search_context(
            self,
            text: str,
            *,
            knowledge_top_k: int,
            assessment_top_k: int,
        ) -> tuple[list[RagSearchMatch], list[RagSearchMatch]]:
            time.sleep(0.05)
            return super().search_context(
                text,
                knowledge_top_k=knowledge_top_k,
                assessment_top_k=assessment_top_k,
            )

    monkeypatch.setattr(
        assessment_agent,
        "_ASSESSMENT_GENERATION_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(AssessmentGenerationTimeoutError, match="timed out"):
        asyncio.run(
            AssessmentAgent(
                agent=FakeAgent("late"),  # ty: ignore[invalid-argument-type]
                embedding_service=SlowEmbeddingService(),  # ty: ignore[invalid-argument-type]
            ).run(FakeResidentContext()),
        )


def test_assessment_agent_does_not_call_model_when_retrieval_fails() -> None:
    fake_agent = FakeAgent("must not be returned")

    class FailingEmbeddingService(FakeEmbeddingService):
        def search_context(
            self,
            text: str,
            *,
            knowledge_top_k: int,
            assessment_top_k: int,
        ) -> tuple[list[RagSearchMatch], list[RagSearchMatch]]:
            assert text
            assert knowledge_top_k == 3  # noqa: PLR2004
            assert assessment_top_k == 5  # noqa: PLR2004
            message = "vector index unavailable"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="vector index unavailable"):
        asyncio.run(
            AssessmentAgent(
                agent=fake_agent,  # ty: ignore[invalid-argument-type]
                embedding_service=FailingEmbeddingService(),  # ty: ignore[invalid-argument-type]
            ).run(FakeResidentContext()),
        )

    assert fake_agent.prompt == ""


def test_assessment_agent_normalizes_whitespace_only_context() -> None:
    fake_agent = FakeAgent("Assessment")
    resident = FakeResidentContext({"resident_id": 7})

    asyncio.run(
        AssessmentAgent(
            agent=fake_agent,  # ty: ignore[invalid-argument-type]
            embedding_service=FakeEmbeddingService(),  # ty: ignore[invalid-argument-type]
        ).run(resident, " \n\t "),
    )

    payload = json.loads(fake_agent.prompt)
    assert resident.summary_contexts == [None]
    assert payload["optional_context"] is None


def test_assessment_agent_bounds_and_sanitizes_retrieved_matches() -> None:
    fake_agent = FakeAgent("Assessment")

    class LargeMatchEmbeddingService(FakeEmbeddingService):
        def search_context(
            self,
            text: str,
            *,
            knowledge_top_k: int,
            assessment_top_k: int,
        ) -> tuple[list[RagSearchMatch], list[RagSearchMatch]]:
            assert text
            assert knowledge_top_k == 3  # noqa: PLR2004
            assert assessment_top_k == 5  # noqa: PLR2004
            return (
                [_match("manual.pdf", "guidance " * 2_000)],
                [_match("assessment.pdf", "example " * 3_000)],
            )

    asyncio.run(
        AssessmentAgent(
            agent=fake_agent,  # ty: ignore[invalid-argument-type]
            embedding_service=LargeMatchEmbeddingService(),  # ty: ignore[invalid-argument-type]
        ).run(FakeResidentContext()),
    )

    payload = json.loads(fake_agent.prompt)
    for key in ("retrieved_knowledge", "previous_assessments"):
        match = payload[key][0]
        assert set(match) == {"filename", "chunk_text", "similarity"}
        assert match["chunk_text"].endswith("[truncated]")


def test_assessment_prompt_defines_inputs_and_style() -> None:
    prompt = (
        pathlib.Path(__file__).parents[2]
        / "src/ntk/agents/prompts/assessment_prompt.md"
    ).read_text(encoding="utf-8")

    assert "## Inputs and evidence" in prompt
    assert "`resident_context`" in prompt
    assert "`comparison`" in prompt
    assert "`retrieved_knowledge`" in prompt
    assert "`previous_assessments`" in prompt
    assert "## Style" in prompt
    assert "## Final validation" in prompt
    assert "Do not add a `Care Coordination:` section" in prompt
    assert "(current - prior) / prior x 100" in prompt
    assert "Do not present an old diet" in prompt
    assert "Suggest protein supplementation based on wound size" in prompt
    assert "no dosage or other SIG details" in prompt
    assert "grouped by indication" in prompt
    assert "include only nutrition-relevant results" in prompt
    assert "MUST trigger at least one new or intensified" in prompt
    assert "merely relist the current interventions as continuations" in prompt
    assert "continuation of existing interventions alone fails" in prompt
    assert "do not satisfy the new-nutrition-intervention requirement" in prompt
    assert "monitoring/evaluation alone is insufficient" in prompt
    assert "always state `Malnutrition status:`" in prompt
    assert (
        "Every note MUST contain exactly one explicit `Malnutrition status:`" in prompt
    )
    assert "no current malnutrition risk identified from supplied data" in prompt
    assert "Missing active diet order" in prompt
    assert "always make a new diet-order recommendation" in prompt
    assert "immediate recommendation to clarify the diet order" in prompt
    assert "Every recommendation must include a concise resident-specific" in prompt
    assert "no recommendation is presented without a rationale" in prompt
    assert "every abnormal value" in prompt
    assert "briefly interpret each abnormal result" in prompt
