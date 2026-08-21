from __future__ import annotations

from ntk.controllers.rag.app import RagControllerGroup
from ntk.controllers.rag.ingest import IngestController


def test_rag_controller_group_exposes_ingest_command() -> None:
    group = RagControllerGroup()

    assert group.name == "rag"
    assert len(group.subcommands) == 1
    assert isinstance(group.subcommands[0], IngestController)
