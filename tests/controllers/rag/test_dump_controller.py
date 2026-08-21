from __future__ import annotations

import typing

import pytest

from ntk.controllers.rag import ingest
from ntk.controllers.rag.ingest import IngestController, IngestOptions
from ntk.models.document import Document, StoredDocumentType

if typing.TYPE_CHECKING:
    import pathlib


class FakeDocumentService:
    """Return detached documents without embedding or persistence."""

    paths: list[pathlib.Path] = []  # noqa: RUF012

    def __init__(self, repository: object) -> None:
        del repository

    def ingest(
        self,
        path: pathlib.Path,
        document_type: StoredDocumentType,
        *,
        overwrite: bool,
    ) -> Document:
        del overwrite
        self.paths.append(path)
        return Document(
            filename=path.name,
            document_type=document_type,
            file_hash=path.name,
        )


def test_ingest_controller_processes_supported_folder_files(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "first.pdf").touch()
    (tmp_path / "second.txt").touch()
    (tmp_path / "ignored.csv").touch()
    FakeDocumentService.paths = []
    monkeypatch.setattr(ingest, "DocumentService", FakeDocumentService)

    output = IngestController(repository=object()).run(
        IngestOptions(
            path=tmp_path,
            document_type=StoredDocumentType.ASSESSMENT,
        ),
    )

    assert [document.filename for document in output.result.documents] == [
        "first.pdf",
        "second.txt",
    ]
    assert [path.name for path in FakeDocumentService.paths] == [
        "first.pdf",
        "second.txt",
    ]


def test_ingest_controller_rejects_missing_path(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        IngestController(repository=object()).run(
            IngestOptions(
                path=tmp_path / "missing",
                document_type=StoredDocumentType.ASSESSMENT,
            ),
        )


def test_ingest_controller_rejects_unsupported_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "document.csv"
    path.touch()

    with pytest.raises(ValueError, match="not a PDF or text file"):
        IngestController(repository=object()).run(
            IngestOptions(
                path=path,
                document_type=StoredDocumentType.ASSESSMENT,
            ),
        )
