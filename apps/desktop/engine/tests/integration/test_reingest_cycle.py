"""A zero-fact ingest is recorded as not applicable and is not redone."""

from __future__ import annotations

import asyncio
import typing

import pymupdf
from sqlmodel import Session, SQLModel, create_engine, select

from engine.models.sql.clinical_source import ClinicalSource, ExtractionStatus
from engine.models.sql.document import Document
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.repositories.clinical_source_repo import ClinicalSourceRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib

    import pytest


def _pipeline(session: Session) -> PersonIngestionPipeline:
    return PersonIngestionPipeline(
        clinical_source_repository=ClinicalSourceRepo(session),
        person_service=PersonService(PersonRepo(session)),
    )


def test_a_zero_fact_ingest_is_finished_and_is_not_retried(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(db_engine)
    report = _weight_report(tmp_path)

    # Empty extraction is a successful assertion that this document contains
    # no applicable clinical facts. Actual extraction errors are represented
    # by a FAILED source and remain retryable.
    with Session(db_engine, expire_on_commit=False) as session:
        pipeline = _pipeline(session)

        async def extracts_nothing(
            _path: pathlib.Path,
            **_kwargs: object,
        ) -> list[typing.Never]:
            return []

        monkeypatch.setattr(pipeline, "_extract_report", extracts_nothing)
        asyncio.run(pipeline.ingest(files=[report]))

        sources = session.exec(select(ClinicalSource)).all()
        assert len(sources) == 1
        assert sources[0].extraction_status is ExtractionStatus.NOT_APPLICABLE
        checksum = session.exec(select(Document.checksum)).one()
        assert PersonRepo(session).document_exists(checksum) is True
        assert PersonRepo(session).document_ingestion_is_complete(checksum) is True

    # A second run skips the completed document, including its empty outcome.
    with Session(db_engine, expire_on_commit=False) as session:
        result = asyncio.run(_pipeline(session).ingest(files=[report]))

        assert result.documents == []
        assert len(session.exec(select(ClinicalSource)).all()) == 1
        assert len(session.exec(select(Document)).all()) == 1, "one row per file"


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
