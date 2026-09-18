from __future__ import annotations

import asyncio
import typing

import pytest

from engine.controllers.documents import ingest
from engine.controllers.documents.ingest import (
    DocumentIngestController,
    DocumentIngestOptions,
)
from engine.pipelines.person.ingestion.transformer import PersonTransformationResult

if typing.TYPE_CHECKING:
    import pathlib


class Upload:
    filename = "document.txt"
    content = b"person report"

    async def read(self) -> bytes:
        return self.content


def test_document_ingest_accepts_multiple_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_paths: list[pathlib.Path] = []

    class Service:
        async def ingest(
            self,
            files: list[pathlib.Path],
            **kwargs: object,
        ) -> PersonTransformationResult:
            assert kwargs.get("person_id") is None
            observed_paths.extend(files)
            assert all(path.is_file() for path in files)
            return PersonTransformationResult(documents=[])

    monkeypatch.setattr(ingest, "ClinicalNoteRepo", lambda session: session)
    monkeypatch.setattr(ingest, "PersonRepo", lambda session: session)
    monkeypatch.setattr(ingest, "PersonIngestionPipeline", lambda **_: Service())
    controller = DocumentIngestController(session=object())  # ty: ignore[invalid-argument-type]
    first_upload = Upload()
    first_upload.filename = "document.txt"
    second_upload = Upload()
    second_upload.filename = "document.txt"
    second_upload.content = b"second person report"

    output = asyncio.run(
        controller.run(DocumentIngestOptions(files=[first_upload, second_upload])),
    )

    assert len(observed_paths) == 2  # noqa: PLR2004
    assert [path.name for path in observed_paths] == [
        "document.txt",
        "document-2.txt",
    ]
    assert output.controller == "ingest"
    assert output.result.documents == []
    assert all(not path.exists() for path in observed_paths)


def test_document_ingest_uses_configured_parallel_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_configuration: list[tuple[object, int]] = []

    class Handler:
        def __init__(self, *, mode: object, workers: int) -> None:
            observed_configuration.append((mode, workers))

        @staticmethod
        def map(
            function: typing.Callable[[pathlib.Path], PersonTransformationResult],
            paths: list[pathlib.Path],
        ) -> list[PersonTransformationResult]:
            return [function(path) for path in paths]

    def ingest_one(path: pathlib.Path) -> PersonTransformationResult:
        assert path.is_file()
        return PersonTransformationResult(documents=[])

    monkeypatch.setattr(ingest, "ParallelPoolHandler", Handler)
    monkeypatch.setattr(ingest, "_ingest_document", ingest_one)
    first_upload = Upload()
    first_upload.filename = "first.txt"
    second_upload = Upload()
    second_upload.filename = "second.txt"
    second_upload.content = b"second person report"

    output = asyncio.run(
        DocumentIngestController().run(
            DocumentIngestOptions(files=[first_upload, second_upload]),
        ),
    )

    assert observed_configuration == [
        (
            ingest.SETTINGS.document_ingestion_pool_mode,
            ingest.SETTINGS.document_ingestion_workers,
        ),
    ]
    assert output.result.documents == []


def test_document_ingest_with_person_id_forwards_known_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_kwargs: dict[str, object] = {}

    class Person:
        name = "Jane Doe"
        date_of_birth = "1950-01-01"

    class PersonRepository:
        def __init__(self, session: object) -> None:
            del session

        @staticmethod
        def get_by_id(person_id: int) -> Person | None:
            assert person_id == 7  # noqa: PLR2004
            return Person()

    class Service:
        def __init__(self, **_kwargs: object) -> None:
            pass

        @staticmethod
        async def ingest(**kwargs: object) -> PersonTransformationResult:
            observed_kwargs.update(kwargs)
            return PersonTransformationResult(documents=[])

    monkeypatch.setattr(ingest, "ClinicalNoteRepo", lambda session: session)
    monkeypatch.setattr(ingest, "PersonRepo", PersonRepository)
    monkeypatch.setattr(ingest, "PersonIngestionPipeline", lambda **_: Service())
    controller = DocumentIngestController(session=object())  # ty: ignore[invalid-argument-type]

    output = asyncio.run(
        controller.run(
            DocumentIngestOptions(files=[Upload()], person_id=7),
        ),
    )

    assert output.result.documents == []
    assert observed_kwargs["person_id"] == 7  # noqa: PLR2004
    assert observed_kwargs["source_person_name"] == "Jane Doe"
    assert observed_kwargs["date_of_birth"] == "1950-01-01"


def test_document_ingest_with_unknown_person_id_raises_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PersonRepository:
        def __init__(self, session: object) -> None:
            del session

        @staticmethod
        def get_by_id(_person_id: int) -> None:
            return None

    monkeypatch.setattr(ingest, "ClinicalNoteRepo", lambda session: session)
    monkeypatch.setattr(ingest, "PersonRepo", PersonRepository)
    controller = DocumentIngestController(session=object())  # ty: ignore[invalid-argument-type]

    with pytest.raises(LookupError, match="Person 99 was not found"):
        asyncio.run(
            controller.run(
                DocumentIngestOptions(files=[Upload()], person_id=99),
            ),
        )
