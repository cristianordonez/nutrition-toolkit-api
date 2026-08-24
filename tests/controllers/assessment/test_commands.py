from __future__ import annotations

import asyncio
import typing
from hashlib import sha256
from types import SimpleNamespace

import pytest

from ntk.controllers.assessment import ingest
from ntk.controllers.assessment.generate import GenerateController, GenerateOptions
from ntk.controllers.assessment.ingest import (
    AssessmentIngestController,
    AssessmentIngestOptions,
    AssessmentIngestResponse,
)
from ntk.models.resident_data import ResidentContext
from ntk.models.sql.assessment import (
    Assessment,
    AssessmentSource,
)
from ntk.models.sql.resident import ResidentSnapshot

if typing.TYPE_CHECKING:
    import pathlib


def test_generate_controller_extracts_retrieves_and_generates_assessment(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "resident.pdf"
    path.write_bytes(b"pdf")
    resident_data = ResidentContext(resident_snapshot=ResidentSnapshot())

    class Agent:
        async def extract(
            self,
            files: list[pathlib.Path],
            context: str | None,
        ) -> ResidentContext:
            assert files == [path]
            assert context == "wound"
            return resident_data

    class Search:
        def run(self, options: object) -> object:
            assert "wound" in str(options)
            return SimpleNamespace(result=SimpleNamespace(matches=[]))

    class Admission:
        async def generate(self, *args: object) -> Assessment:
            assert args == (resident_data, [], [], "wound")
            return Assessment(
                source=AssessmentSource.GENERATED,
                source_filename=None,
                content="Completed assessment",
                content_hash=sha256(b"Completed assessment").hexdigest(),
                assessment_index=0,
                created_by="gpt-4.1",
            )

    controller = GenerateController(
        resident_data_agent=Agent(),  # ty: ignore[invalid-argument-type]
        admission_agent=Admission(),  # ty: ignore[invalid-argument-type]
        knowledge_search=Search(),  # ty: ignore[invalid-argument-type]
        assessment_search=Search(),  # ty: ignore[invalid-argument-type]
    )
    output = asyncio.run(
        controller.run(GenerateOptions(files=[path], context="wound")),
    )
    assert output.result.content == "Completed assessment"
    assert output.result.to_console() == "Completed assessment"


def test_assessment_ingest_uses_fixed_document_type(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "assessment.pdf"
    path.touch()

    class Service:
        def __init__(self, assessment_repository: object) -> None:
            assert assessment_repository == "repository"

        def ingest_assessment(
            self,
            document_path: pathlib.Path,
            *,
            overwrite: bool,
            created_by: str,
        ) -> list[Assessment]:
            assert document_path == path
            assert overwrite is False
            assert created_by == "self"
            return [
                Assessment(
                    source=AssessmentSource.UPLOADED,
                    source_filename=document_path.name,
                    content="Nutrition assessment",
                    content_hash="hash",
                    assessment_index=0,
                    created_by=created_by,
                ),
            ]

    monkeypatch.setattr(ingest, "DocumentExtractorService", Service)
    output = AssessmentIngestController(
        repository="repository",  # ty: ignore[invalid-argument-type]
    ).run(AssessmentIngestOptions(path=path))
    assert output.controller == "ingest"
    assert output.result.to_console() == "# assessment.pdf"


def test_assessment_ingest_rejects_invalid_path(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        AssessmentIngestController._get_file_paths(  # noqa: SLF001
            tmp_path / "missing.pdf",
        )

    unsupported = tmp_path / "assessment.csv"
    unsupported.touch()
    with pytest.raises(ValueError, match="not a PDF or text file"):
        AssessmentIngestController._get_file_paths(unsupported)  # noqa: SLF001


def test_assessment_ingest_response_renders_empty_documents() -> None:
    response = AssessmentIngestResponse(documents=[])

    assert response.to_console() == ""
    assert response.chunk_count == 0
    assert response.model_dump()["chunk_count"] == 0
