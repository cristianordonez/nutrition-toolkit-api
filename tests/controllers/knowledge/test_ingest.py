from __future__ import annotations

import asyncio
import typing

import pytest

from ntk.controllers.knowledge import ingest
from ntk.controllers.knowledge.app import KnowledgeControllerGroup
from ntk.controllers.knowledge.ingest import (
    KnowledgeIngestController,
    KnowledgeIngestOptions,
    KnowledgeIngestResponse,
)
from ntk.models.knowledge import KnowledgeType
from ntk.models.sql.knowledge import Knowledge

if typing.TYPE_CHECKING:
    import pathlib


class ResidentExtractionService:
    paths: typing.ClassVar[list[pathlib.Path]] = []
    document_types: typing.ClassVar[list[KnowledgeType]] = []

    def __init__(self, knowledge_repository: object) -> None:
        assert knowledge_repository == "repository"

    async def ingest_knowledge(
        self,
        path: pathlib.Path,
        document_type: KnowledgeType,
        *,
        overwrite: bool,
    ) -> Knowledge:
        assert overwrite is True
        self.paths.append(path)
        self.document_types.append(document_type)
        return Knowledge(
            filename=path.name,
            knowledge_type=document_type,
            file_hash=path.name,
        )


def test_knowledge_group_and_ingest_controller(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "manual.pdf").touch()
    (tmp_path / "notes.txt").touch()
    (tmp_path / "ignored.csv").touch()
    ResidentExtractionService.paths = []
    ResidentExtractionService.document_types = []
    monkeypatch.setattr(
        ingest,
        "ResidentIngestionService",
        ResidentExtractionService,
    )
    monkeypatch.setattr(ingest, "KnowledgeRepo", lambda _session: "repository")
    group = KnowledgeControllerGroup()
    assert isinstance(group.subcommands[0], KnowledgeIngestController)

    output = asyncio.run(
        KnowledgeIngestController(session=object()).run(  # ty: ignore[invalid-argument-type]
            KnowledgeIngestOptions(
                path=tmp_path,
                document_type="diet-manual",
                overwrite=True,
            ),
        ),
    )
    assert output.controller == "ingest"
    assert [path.name for path in ResidentExtractionService.paths] == [
        "manual.pdf",
        "notes.txt",
    ]
    assert ResidentExtractionService.document_types == [
        KnowledgeType.DIET_MANUAL,
        KnowledgeType.DIET_MANUAL,
    ]
    assert output.result.to_console() == "# manual.pdf\n# notes.txt"


@pytest.mark.parametrize(
    ("filename", "message"),
    [("missing.pdf", "does not exist"), ("manual.csv", "not a PDF")],
)
def test_knowledge_ingest_rejects_invalid_path(
    tmp_path: pathlib.Path,
    filename: str,
    message: str,
) -> None:
    path = tmp_path / filename
    if path.suffix == ".csv":
        path.touch()
    with pytest.raises(ValueError, match=message):
        KnowledgeIngestController._get_file_paths(path)  # noqa: SLF001


def test_knowledge_ingest_response_renders_empty_documents() -> None:
    assert KnowledgeIngestResponse(documents=[]).to_console() == ""
