from __future__ import annotations

import asyncio
import typing

import pymupdf
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.controllers.assessment.generate import (
    AssessmentGenerationOptions,
    PersonAssessmentGenerationOptions,
)
from ntk.controllers.documents.ingest import DocumentIngestController
from ntk.models.sql.facility import Facility
from ntk.models.sql.person import (
    PersonAssessmentEmbedding,
    PersonWeight,
)
from ntk.pipelines.assessment.create import pipeline as generation_service
from ntk.presentation.api.routers import assessments, documents
from ntk.repositories.facility_repo import FacilityRepo

if typing.TYPE_CHECKING:
    import pathlib

    import pytest

    from ntk.models.assessment_context import BudgetedAssessmentContext


class Upload:
    filename = "weights.pdf"

    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self) -> bytes:
        return self.content


def test_ingestion_then_generation_uses_persisted_person_data(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_weight = 142
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    pdf = _weight_report(tmp_path)

    with Session(engine, expire_on_commit=False) as ingestion_session:
        FacilityRepo(ingestion_session).create(
            Facility(facility_identifier="FAC-1", name="Sunrise Care"),
        )
        monkeypatch.setattr(
            documents,
            "DocumentIngestController",
            lambda: DocumentIngestController(ingestion_session),
        )

        ingestion_result = asyncio.run(
            documents.ingest_documents([Upload(pdf.read_bytes())]),  # ty: ignore[invalid-argument-type]
        )

        assert len(ingestion_result.documents) == 1
        stored_weight = ingestion_session.exec(select(PersonWeight)).one()
        person_id = stored_weight.person_id
        assert stored_weight.weight_lb == expected_weight

    class Agent:
        captured_payload: typing.ClassVar[dict[str, object] | None] = None

        def __init__(self, **_kwargs: object) -> None:
            pass

        @classmethod
        async def run(
            cls,
            assessment_context: BudgetedAssessmentContext,
        ) -> str:
            assert assessment_context.additional_context == "annual nutrition review"
            cls.captured_payload = assessment_context.model_dump(mode="json")
            return "Generated from persisted person data"

    class Embedding:
        def __init__(self, _repository: object) -> None:
            pass

        def search_assessments(
            self,
            _query: str,
            *,
            top_k: int,
        ) -> list[object]:
            assert top_k > 0
            return []

    monkeypatch.setattr(generation_service, "AssessmentAgent", Agent)
    monkeypatch.setattr(generation_service, "EmbeddingService", Embedding)

    with Session(engine, expire_on_commit=False) as generation_session:
        generated = asyncio.run(
            assessments.generate_assessments(
                AssessmentGenerationOptions(
                    persons=[
                        PersonAssessmentGenerationOptions(
                            source_person_identifier="R1",
                            facility_identifier="FAC-1",
                            context="annual nutrition review",
                        ),
                    ],
                ),
                generation_session,
            ),
        )

        assert len(generated) == 1
        assert generated[0].person_id == person_id
        assert generated[0].person_name == "Person One"
        assert generated[0].content == "Generated from persisted person data"
        assert generation_session.exec(select(PersonAssessmentEmbedding)).all() == []

    assert Agent.captured_payload is not None
    person_payload = typing.cast(
        "dict[str, object]",
        Agent.captured_payload["person"],
    )
    assert person_payload["name"] == "Person One"
    weights = typing.cast(
        "list[dict[str, object]]",
        person_payload["weight_history"],
    )
    assert len(weights) == 1
    assert weights[0]["measured_at"] == "2026-08-24T22:17:00"
    assert weights[0]["weight_lb"] == expected_weight
    assert weights[0]["description"] == "Standing"


def _weight_report(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "weights.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=900, height=700)
        for index, line in enumerate(
            (
                "Weights and Vitals Summary",
                "Sunrise Care",
                "Resident: Person One (R1)",
                "Vital: Height, Weight",
                "Weight Summary",
                "08/24/2026 22:17 142 Lbs (Standing)",
            ),
        ):
            page.insert_text((20, 40 + (index * 18)), line, fontsize=8)
        document.save(path)
    return path
