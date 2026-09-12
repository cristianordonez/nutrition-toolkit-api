from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pytest

from ntk.models.extracted_fact_create import (
    ExtractedFactCreate,
    LabPayload,
    WeightPayload,
)
from ntk.pipelines.demo import assessment as demo
from ntk.pipelines.demo.assessment import DemoAssessmentPipeline, NoDemoFactsError
from ntk.services.person.detail_builder import PersonDetailBuilder

if typing.TYPE_CHECKING:
    from pathlib import Path

    from ntk.models.assessment_context import BudgetedAssessmentContext


_OBSERVED_AT = datetime(2026, 9, 1, tzinfo=UTC)


class EmbeddingService:
    def __init__(self) -> None:
        self.summaries: list[str] = []

    async def search_assessments_async(
        self,
        text: str,
        *,
        top_k: int,
    ) -> list[typing.Never]:
        assert top_k == 5  # noqa: PLR2004
        self.summaries.append(text)
        return []


class AssessmentAgent:
    def __init__(self) -> None:
        self.context: BudgetedAssessmentContext | None = None

    async def run(self, context: BudgetedAssessmentContext) -> str:
        self.context = context
        return "Generated from transient facts"


class Extractor:
    def __init__(self, facts: list[ExtractedFactCreate]) -> None:
        self.facts = facts

    async def extract(self) -> list[ExtractedFactCreate]:
        return self.facts


class DemoExtractor(Extractor):
    async def extract(self) -> list[ExtractedFactCreate]:
        message = "Demo pipeline used identity-strict extraction"
        raise AssertionError(message)

    async def extract_for_demo(self) -> list[ExtractedFactCreate]:
        return self.facts


def _pipeline(
    embedding_service: EmbeddingService,
    assessment_agent: AssessmentAgent,
) -> DemoAssessmentPipeline:
    return DemoAssessmentPipeline(
        typing.cast("typing.Any", object()),
        typing.cast("typing.Any", embedding_service),
        detail_builder=PersonDetailBuilder(),
        assessment_agent=typing.cast("typing.Any", assessment_agent),
    )


def test_demo_combines_facts_without_resolving_or_persisting_person(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weights_path = tmp_path / "weights.txt"
    weights_path.write_text("weights", encoding="utf-8")
    labs_path = tmp_path / "labs.txt"
    labs_path.write_text("labs", encoding="utf-8")
    facts_by_path = {
        weights_path: [
            ExtractedFactCreate(
                payload=WeightPayload(weight_lb=150, measured_at=_OBSERVED_AT),
                confidence=1,
            ),
        ],
        labs_path: [
            ExtractedFactCreate(
                payload=LabPayload(
                    name="Albumin",
                    result="3.4",
                    observed_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
        ],
    }
    monkeypatch.setattr(
        demo,
        "get_person_extractor",
        lambda path: Extractor(facts_by_path[path]),
    )
    embedding_service = EmbeddingService()
    assessment_agent = AssessmentAgent()

    result = asyncio.run(
        _pipeline(embedding_service, assessment_agent).run_paths(
            [weights_path, labs_path],
        ),
    )

    assert result.person.id is None
    assert result.person.name == "Demo person"
    assert result.detail.person_id is None
    assert result.detail.current_weight is not None
    assert result.detail.current_weight.weight_lb == 150  # noqa: PLR2004
    assert [lab.name for lab in result.detail.labs] == ["Albumin"]
    assert result.ingestion.facts_extracted == 2  # noqa: PLR2004
    assert result.ingestion.facts_persisted == 0
    assert all(item.document_id is None for item in result.ingestion.documents)
    assert all(item.facts_persisted == 0 for item in result.ingestion.documents)
    assert result.assessment.id is None
    assert result.assessment.person_id is None
    assert result.assessment.content == "Generated from transient facts"
    assert assessment_agent.context is not None
    assert embedding_service.summaries


def test_demo_uses_optional_identity_metadata_without_database_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("nutrition note", encoding="utf-8")
    fact = ExtractedFactCreate(
        source_person_name="Doe, Jane",
        source_person_identifier="R-7",
        facility_name="Demo Facility",
        payload=WeightPayload(weight_lb=145, measured_at=_OBSERVED_AT),
        confidence=1,
    )
    monkeypatch.setattr(demo, "get_person_extractor", lambda _path: Extractor([fact]))

    result = asyncio.run(
        _pipeline(EmbeddingService(), AssessmentAgent()).run_path(path),
    )

    assert result.person.id is None
    assert result.person.name == "Doe, Jane"
    assert result.person.person_identifier == "R-7"
    assert result.person.facility_name == "Demo Facility"


def test_demo_pipeline_uses_relaxed_extractor_entry_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deidentified.txt"
    path.write_text("weight report without identity", encoding="utf-8")
    fact = ExtractedFactCreate(
        payload=WeightPayload(weight_lb=145, measured_at=_OBSERVED_AT),
        confidence=1,
    )
    monkeypatch.setattr(
        demo,
        "get_person_extractor",
        lambda _path: DemoExtractor([fact]),
    )

    result = asyncio.run(
        _pipeline(EmbeddingService(), AssessmentAgent()).run_path(path),
    )

    assert result.person.name == "Demo person"
    assert result.ingestion.facts_extracted == 1


def test_demo_rejects_documents_without_extractable_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("empty", encoding="utf-8")
    monkeypatch.setattr(demo, "get_person_extractor", lambda _path: Extractor([]))

    with pytest.raises(NoDemoFactsError, match="extractable clinical facts"):
        asyncio.run(
            _pipeline(EmbeddingService(), AssessmentAgent()).run_path(path),
        )
