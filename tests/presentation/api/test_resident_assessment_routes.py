from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ntk.controllers.assessment.ingest import (
    AssessmentIngestResponse,
)
from ntk.controllers.assessment.search import (
    AssessmentSearchResponse,
)
from ntk.models.rag import RagSearchMatch
from ntk.models.resident_data import ResidentContext
from ntk.models.sql.assessment import (
    Assessment,
    AssessmentSource,
)
from ntk.models.sql.resident import ResidentSnapshot
from ntk.presentation.api.routers import assessment, resident

_SEARCH_LIMIT = 4


class Upload:
    def __init__(self, filename: str | None, contents: bytes = b"pdf") -> None:
        self.filename = filename
        self.contents = contents

    async def read(self) -> bytes:
        return self.contents


def _resident_data() -> ResidentContext:
    return ResidentContext(resident_snapshot=ResidentSnapshot(age=70))


def _assessment(filename: str | None, content: str) -> Assessment:
    return Assessment(
        source=(
            AssessmentSource.UPLOADED
            if filename is not None
            else AssessmentSource.GENERATED
        ),
        source_filename=filename,
        content=content,
        content_hash=f"hash-{content}",
        assessment_index=0,
        created_by="dietitian",
    )


def test_resident_extract_route_passes_files_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _resident_data()

    class Controller:
        async def run_uploads(
            self,
            files: list[Upload],
            context: str | None,
        ) -> object:
            assert len(files) == 1
            assert files[0].filename == "resident.pdf"
            assert context == "dialysis"
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(resident, "_RESIDENT_EXTRACT_CONTROLLER", Controller())
    result = asyncio.run(
        resident.extract_resident_data(
            [Upload("resident.pdf")],  # ty: ignore[invalid-argument-type]
            "dialysis",
        ),
    )
    assert result is expected


def test_resident_extract_route_accepts_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _resident_data()

    class Controller:
        async def run_uploads(
            self,
            files: list[Upload],
            context: str | None,
        ) -> object:
            assert len(files) == 1
            assert files[0].filename == "resident.csv"
            assert context is None
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(resident, "_RESIDENT_EXTRACT_CONTROLLER", Controller())
    result = asyncio.run(
        resident.extract_resident_data(
            [Upload("resident.csv", b"weight_lb\n120")],  # ty: ignore[invalid-argument-type]
        ),
    )
    assert result is expected


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "At least one"),
        ([Upload("resident.txt")], "not a PDF or CSV"),
        ([Upload("resident.pdf", b"")], "is empty"),
    ],
)
def test_resident_extract_route_rejects_invalid_files(
    files: list[Upload],
    message: str,
) -> None:
    with pytest.raises(HTTPException, match=message):
        asyncio.run(
            resident.extract_resident_data(
                files,  # ty: ignore[invalid-argument-type]
            ),
        )


def test_generate_assessment_route_uses_generate_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _assessment(None, "Completed assessment")

    class Controller:
        async def run_uploads(
            self,
            files: list[Upload],
            context: str | None,
        ) -> object:
            assert context == "wounds"
            assert len(files) == 1
            assert files[0].filename == "resident.pdf"
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(assessment, "_GENERATE_CONTROLLER", Controller())
    result = asyncio.run(
        assessment.generate_assessment(
            [Upload("resident.pdf")],  # ty: ignore[invalid-argument-type]
            "wounds",
        ),
    )
    assert result is expected


def test_assessment_ingest_route_uses_assessment_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = AssessmentIngestResponse(
        documents=[
            _assessment("assessment.pdf", "Nutrition assessment"),
        ],
    )

    class Controller:
        async def run_uploads(
            self,
            files: list[Upload],
            *,
            overwrite: bool,
            created_by: str,
        ) -> object:
            assert len(files) == 1
            assert files[0].filename == "assessment.pdf"
            assert overwrite is True
            assert created_by == "consultant"
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(assessment, "_ASSESSMENT_INGEST_CONTROLLER", Controller())
    result = asyncio.run(
        assessment.ingest_assessments(
            [Upload("assessment.pdf")],  # ty: ignore[invalid-argument-type]
            overwrite=True,
            created_by="consultant",
        ),
    )
    assert result is expected
    assert result.documents[0].source_filename == "assessment.pdf"


def test_assessment_search_route_uses_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _assessment("assessment.pdf", "ADIME")
    match = RagSearchMatch(
        document_id=document.id,
        filename=document.source_filename or "generated-assessment",
        chunk_text="ADIME",
        similarity=0.9,
    )

    class Controller:
        def search(self, text: str, top_k: int) -> object:
            assert text == "weight loss"
            assert top_k == _SEARCH_LIMIT
            return SimpleNamespace(result=AssessmentSearchResponse(matches=[match]))

    monkeypatch.setattr(assessment, "_ASSESSMENT_SEARCH_CONTROLLER", Controller())
    assert assessment.search_assessments("weight loss", _SEARCH_LIMIT) == [match]


def test_assessment_search_route_rejects_blank_text() -> None:
    with pytest.raises(HTTPException, match="must not be empty"):
        assessment.search_assessments(" ", 5)
