from __future__ import annotations

import argparse
import asyncio
import typing

from engine.controllers.ncp import search as search_module
from engine.controllers.ncp.search import NCPSearchOptions, NCPVectorSearchController
from engine.models.ncp_note import NCPNoteType
from engine.models.rag import RagSearchMatch

if typing.TYPE_CHECKING:
    import pytest


def test_search_command_returns_matching_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, NCPNoteType | None]] = []

    class Embeddings:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def search_examples_async(
            text: str,
            top_k: int,
            *,
            note_type: NCPNoteType | None = None,
        ) -> list[RagSearchMatch]:
            calls.append((text, top_k, note_type))
            return [
                RagSearchMatch(
                    document_id=7,
                    filename="quarterly",
                    chunk_text="Weight stable.",
                    similarity=0.91,
                    section_title="NCP example",
                ),
            ]

    monkeypatch.setattr(search_module, "EmbeddingService", Embeddings)

    output = asyncio.run(
        NCPVectorSearchController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(
            NCPSearchOptions(
                text="weight",
                top_k=3,
                note_type=NCPNoteType.QUARTERLY,
            ),
        ),
    )

    assert calls == [("weight", 3, NCPNoteType.QUARTERLY)]
    assert output.result.to_console() == (
        "# quarterly | note 7 (0.9100)\nWeight stable."
    )


def test_search_command_parses_note_type() -> None:
    parser = argparse.ArgumentParser()
    NCPVectorSearchController().add_arguments(parser)

    args = parser.parse_args(["--text", "weight", "--note-type", "wound"])

    assert args.text == "weight"
    assert NCPSearchOptions(**vars(args)).note_type is NCPNoteType.WOUND
