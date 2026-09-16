from __future__ import annotations

import asyncio
import typing
from datetime import date

import pytest

from api.agents.ncp_agent import NCP_MODEL
from api.models.rag import RagSearchMatch
from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
)
from api.pipelines.ncp.create import pipeline as generation_pipeline
from api.pipelines.ncp.create.pipeline import FinalizedNCPError
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


def _ncp(
    *,
    status: NutritionCareProcessStatus = NutritionCareProcessStatus.DRAFT,
) -> NutritionCareProcess:
    return NutritionCareProcess(
        id=1,
        person_identifier="R1",
        note_text="Original",
        content_hash="old-hash",
        created_by="model",
        status=status,
    )


def test_finalize_creates_an_embedding_for_the_finalized_ncp() -> None:
    ncp = _ncp(status=NutritionCareProcessStatus.FINALIZED)

    class Repository:
        updated: typing.ClassVar[list[NutritionCareProcess]] = []

        @staticmethod
        def finalize_ncp(
            ncp_id: int,
            person_identifier: str,
        ) -> NutritionCareProcess | None:
            assert person_identifier == "R1"
            return ncp if ncp_id == ncp.id else None

        @staticmethod
        def get_embedding(_ncp_id: int) -> None:
            return None

        @classmethod
        def update_ncp(
            cls,
            value: NutritionCareProcess,
            *,
            embedding: list[float],
            embedding_type: NutritionClinicalNoteType,
            model_name: str,
        ) -> NutritionCareProcess:
            assert embedding == [0.1]
            assert embedding_type is NutritionClinicalNoteType.NUTRITION_DIETARY
            assert model_name == "embedding-model"
            cls.updated.append(value)
            return value

    class Embeddings:
        embedding_model = "embedding-model"

        @staticmethod
        async def get_embedding_async(content: str) -> list[float]:
            assert content == ncp.note_text
            return [0.1]

    result = asyncio.run(
        generation_pipeline.NutritionCareProcessPipeline(
            Repository(),  # ty: ignore[invalid-argument-type]
            embedding_service=Embeddings(),  # ty: ignore[invalid-argument-type]
        ).finalize(1, "R1"),
    )

    assert result is ncp
    assert Repository.updated == [ncp]


class _UpdateRepository:
    def __init__(self, ncp: NutritionCareProcess | None) -> None:
        self.ncp = ncp
        self.updated: list[
            tuple[
                NutritionCareProcess,
                list[float] | None,
                NutritionClinicalNoteType | None,
                str | None,
            ]
        ] = []

    def get_ncp(
        self,
        _ncp_id: int,
        _person_identifier: str,
    ) -> NutritionCareProcess | None:
        return self.ncp

    def update_ncp(
        self,
        ncp: NutritionCareProcess,
        *,
        embedding: list[float] | None,
        embedding_type: NutritionClinicalNoteType | None,
        model_name: str | None,
    ) -> NutritionCareProcess:
        self.updated.append((ncp, embedding, embedding_type, model_name))
        return ncp


def test_update_changes_fields_and_refreshes_embedding() -> None:
    ncp = _ncp()
    repository = _UpdateRepository(ncp)

    class Embeddings:
        embedding_model = "embedding-model"

        @staticmethod
        async def get_embedding_async(text: str) -> list[float]:
            assert text == "Updated   assessment"
            return [0.1, 0.2]

    result = asyncio.run(
        generation_pipeline.NutritionCareProcessPipeline(
            repository,  # ty: ignore[invalid-argument-type]
            embedding_service=Embeddings(),  # ty: ignore[invalid-argument-type]
        ).update(
            1,
            "R1",
            note_text="  Updated   assessment  ",
            created_by="  dietitian  ",
            status=NutritionCareProcessStatus.FINALIZED,
        ),
    )

    assert result is ncp
    assert ncp.note_text == "Updated   assessment"
    assert ncp.created_by == "dietitian"
    assert ncp.status is NutritionCareProcessStatus.FINALIZED
    assert ncp.finalized_at is not None
    assert repository.updated == [
        (
            ncp,
            [0.1, 0.2],
            NutritionClinicalNoteType.NUTRITION_DIETARY,
            "embedding-model",
        ),
    ]


def test_update_handles_missing_draft_and_invalid_values() -> None:
    missing = generation_pipeline.NutritionCareProcessPipeline(
        _UpdateRepository(None),  # ty: ignore[invalid-argument-type]
    ).update(999, "R1")
    assert asyncio.run(missing) is None

    ncp = _ncp()
    repository = _UpdateRepository(ncp)

    with pytest.raises(ValueError, match="content cannot be empty"):
        asyncio.run(
            generation_pipeline.NutritionCareProcessPipeline(
                repository,  # ty: ignore[invalid-argument-type]
            ).update(1, "R1", note_text="  "),
        )
    with pytest.raises(ValueError, match="creator cannot be empty"):
        asyncio.run(
            generation_pipeline.NutritionCareProcessPipeline(
                repository,  # ty: ignore[invalid-argument-type]
            ).update(1, "R1", created_by="  "),
        )


def test_editing_finalized_ncp_fails_without_mutating_it() -> None:
    ncp = _ncp(status=NutritionCareProcessStatus.FINALIZED)
    original_content = ncp.note_text
    original_hash = ncp.content_hash
    repository = _UpdateRepository(ncp)

    with pytest.raises(FinalizedNCPError, match="finalized and cannot be edited"):
        asyncio.run(
            generation_pipeline.NutritionCareProcessPipeline(
                repository,  # ty: ignore[invalid-argument-type]
            ).update(1, "R1", note_text="Replacement content"),
        )

    assert ncp.note_text == original_content
    assert ncp.content_hash == original_hash
    assert ncp.status is NutritionCareProcessStatus.FINALIZED
    assert repository.updated == []


def test_finalized_ncp_cannot_transition_back_to_draft() -> None:
    ncp = _ncp(status=NutritionCareProcessStatus.FINALIZED)
    repository = _UpdateRepository(ncp)

    with pytest.raises(FinalizedNCPError, match="finalized and cannot be edited"):
        asyncio.run(
            generation_pipeline.NutritionCareProcessPipeline(
                repository,  # ty: ignore[invalid-argument-type]
            ).update(1, "R1", status=NutritionCareProcessStatus.DRAFT),
        )

    assert ncp.status is NutritionCareProcessStatus.FINALIZED
    assert repository.updated == []


def test_updating_draft_content_does_not_create_embedding() -> None:
    ncp = _ncp()
    repository = _UpdateRepository(ncp)

    result = asyncio.run(
        generation_pipeline.NutritionCareProcessPipeline(
            repository,  # ty: ignore[invalid-argument-type]
        ).update(1, "R1", note_text="Updated draft"),
    )

    assert result is ncp
    assert ncp.status is NutritionCareProcessStatus.DRAFT
    assert repository.updated == [(ncp, None, None, None)]
