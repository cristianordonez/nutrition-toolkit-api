from __future__ import annotations

import asyncio
import typing
from datetime import date

import pytest

from api.agents.ncp_agent import NCP_MODEL
from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
)
from api.models.rag import RagSearchMatch
from api.pipelines.ncp.create import pipeline as generation_pipeline
from ntk.models.derived_calculations import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    TubeFeedCalculation,
)
from ntk.models.ncp_context import BudgetedPersonDetail, NCPGenerationRequest

if typing.TYPE_CHECKING:
    from api.models.ncp_context import BudgetedNCPContext


def _request() -> NCPGenerationRequest:
    return NCPGenerationRequest(
        person_identifier="R1",
        facility_identifier="FAC-1",
        summary_text='{"name":"Doe, Jane"}',
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            derived_calculations=DerivedPersonCalculations(
                calculated_on=date(2026, 9, 7),
                anthropometrics=AnthropometricCalculations(),
                nutrition_needs=NutritionNeedsCalculation(status="not_computed"),
                tube_feed=TubeFeedCalculation(status="not_applicable"),
                parenteral_nutrition=ParenteralNutritionCalculation(
                    status="not_applicable",
                ),
            ),
        ),
        additional_context="wound review",
    )


def test_generate_looks_up_relevant_ncps_and_persists_a_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    captured: list[BudgetedNCPContext] = []

    class Agent:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs == {"embedding_service": embedding_service}

        @staticmethod
        async def run(context: BudgetedNCPContext) -> str:
            captured.append(context)
            return "Generated assessment"

    class Embeddings:
        def __init__(self, _repository: object) -> None:
            pass

        @staticmethod
        async def search_ncps_async(
            text: str,
            person_identifier: str,
            *,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == request.summary_text
            assert person_identifier == "R1"
            assert top_k == 5  # noqa: PLR2004
            return [
                RagSearchMatch(
                    document_id=12,
                    filename="similar-ncp.txt",
                    chunk_text="Similar assessment style",
                    similarity=0.91,
                ),
            ]

    class Repository:
        @staticmethod
        def create_generated_draft(
            ncp: NutritionCareProcess,
        ) -> NutritionCareProcess:
            ncp.id = 31
            return ncp

    monkeypatch.setattr(generation_pipeline, "NutritionCareProcessAgent", Agent)
    embedding_service = Embeddings(object())
    pipeline = generation_pipeline.NutritionCareProcessPipeline(
        Repository(),  # ty: ignore[invalid-argument-type]
        embedding_service=embedding_service,  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(pipeline.generate(request))

    assert len(captured) == 1
    assert captured[0].person.name == request.person.name
    assert captured[0].relevant_ncps[0].document_id == 12  # noqa: PLR2004
    assert captured[0].additional_context == "wound review"
    assert result.id == 31  # noqa: PLR2004
    assert result.person_identifier == "R1"
    assert result.facility_identifier == "FAC-1"
    assert result.note_text == "Generated assessment"
    assert result.created_by == NCP_MODEL
    assert result.ncp_source is NutritionCareProcessSource.GENERATED
    assert result.status is NutritionCareProcessStatus.DRAFT


def test_generate_propagates_retrieval_failure() -> None:
    class Embeddings:
        def __init__(self, _repository: object) -> None:
            pass

        @staticmethod
        async def search_ncps_async(
            _text: str,
            _person_identifier: str,
            *,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert top_k == 5  # noqa: PLR2004
            msg = "vector index unavailable"
            raise RuntimeError(msg)

    pipeline = generation_pipeline.NutritionCareProcessPipeline(
        object(),  # ty: ignore[invalid-argument-type]
        embedding_service=Embeddings(object()),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(RuntimeError, match="vector index unavailable"):
        asyncio.run(pipeline.generate(_request()))


def test_search_relevant_ncps_limits_matches_and_truncates_chunk_text() -> None:
    class Embeddings:
        def __init__(self, _repository: object) -> None:
            pass

        @staticmethod
        async def search_ncps_async(
            _text: str,
            _person_identifier: str,
            *,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert top_k == 5  # noqa: PLR2004
            return [
                RagSearchMatch(
                    document_id=index,
                    filename=f"ncp-{index}.txt",
                    chunk_text="example ncp " * 2_000,
                    similarity=0.9,
                )
                for index in range(8)
            ]

    pipeline = generation_pipeline.NutritionCareProcessPipeline(
        object(),  # ty: ignore[invalid-argument-type]
        embedding_service=Embeddings(object()),  # ty: ignore[invalid-argument-type]
    )

    matches = asyncio.run(
        pipeline._search_relevant_ncps(  # noqa: SLF001
            "summary text",
            "R1",
        ),
    )

    assert len(matches) == 5  # noqa: PLR2004
    assert matches[0].chunk_text.endswith("[truncated]")


def test_sync_ncps_is_deferred() -> None:
    pipeline = generation_pipeline.NutritionCareProcessPipeline(
        object(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(NotImplementedError, match="deferred"):
        asyncio.run(pipeline.sync_ncps())
