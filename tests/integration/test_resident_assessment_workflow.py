from __future__ import annotations

import asyncio
import typing

import pymupdf
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.controllers.assessment.generation import (
    AssessmentGenerationOptions,
    ResidentAssessmentGenerationOptions,
)
from ntk.controllers.documents.ingest import DocumentIngestController
from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import (
    ResidentAssessmentEmbedding,
    ResidentWeight,
)
from ntk.presentation.api.routers import assessments, documents
from ntk.repositories.facility_repo import FacilityRepo
from ntk.services.assessment import generation_service

if typing.TYPE_CHECKING:
    import pathlib

    import pytest

    from ntk.services.assessment.generation_service import _ResidentAgentContext


class Upload:
    filename = "weights.pdf"

    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self) -> bytes:
        return self.content


def test_ingestion_then_generation_uses_persisted_resident_data(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_weight = 142
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    pdf = _weight_report(tmp_path)

    with Session(engine, expire_on_commit=False) as ingestion_session:
        FacilityRepo(ingestion_session).create(
            Facility(facility_id="FAC-1", name="Sunrise Care"),
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
        stored_weight = ingestion_session.exec(select(ResidentWeight)).one()
        resident_id = stored_weight.resident_id
        assert stored_weight.weight_lb == expected_weight

    class Agent:
        captured_payload: typing.ClassVar[dict[str, object] | None] = None

        def __init__(self, **_kwargs: object) -> None:
            pass

        @classmethod
        async def run(
            cls,
            resident_context: _ResidentAgentContext,
            context: str | None = None,
        ) -> str:
            assert context == "annual nutrition review"
            cls.captured_payload = resident_context.llm_payload()
            return "Generated from persisted resident data"

    class Embedding:
        def __init__(self, _repository: object) -> None:
            pass

    monkeypatch.setattr(generation_service, "AssessmentAgent", Agent)
    monkeypatch.setattr(generation_service, "EmbeddingService", Embedding)

    with Session(engine, expire_on_commit=False) as generation_session:
        generated = asyncio.run(
            assessments.generate_assessments(
                AssessmentGenerationOptions(
                    residents=[
                        ResidentAssessmentGenerationOptions(
                            resident_identifier="R1",
                            facility_id="FAC-1",
                            context="annual nutrition review",
                        ),
                    ],
                ),
                generation_session,
            ),
        )

        assert len(generated) == 1
        assert generated[0].resident_id == resident_id
        assert generated[0].resident_name == "Resident One"
        assert generated[0].content == "Generated from persisted resident data"
        assert generation_session.exec(select(ResidentAssessmentEmbedding)).all() == []

    assert Agent.captured_payload is not None
    assert Agent.captured_payload["resident_id"] == resident_id
    assert Agent.captured_payload["resident_name"] == "Resident One"
    weights = typing.cast("list[dict[str, object]]", Agent.captured_payload["weights"])
    assert weights == [
        {
            "resident_facility_stay_id": None,
            "measured_at": "2026-08-24T22:17:00",
            "weight_lb": 142.0,
            "description": "Standing",
        },
    ]
    assert Agent.captured_payload["context_scope"] == {
        "ordering": "reverse_chronological",
        "orders": "active_or_unspecified_status_only",
        "history": "bounded_recent_records",
    }


def _weight_report(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "weights.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=900, height=700)
        for index, line in enumerate(
            (
                "Weights and Vitals Summary",
                "Sunrise Care",
                "Resident: Resident One (R1)",
                "Vital: Height, Weight",
                "Weight Summary",
                "08/24/2026 22:17 142 Lbs (Standing)",
            ),
        ):
            page.insert_text((20, 40 + (index * 18)), line, fontsize=8)
        document.save(path)
    return path
