from __future__ import annotations

from engine.controllers.documents.app import DocumentControllerGroup
from engine.controllers.ncp.app import NCPControllerGroup
from engine.controllers.tubefeed.app import TubefeedControllerGroup


def test_current_controller_groups_expose_their_commands() -> None:
    documents = DocumentControllerGroup()
    ncp = NCPControllerGroup()
    tubefeed = TubefeedControllerGroup()

    assert len(documents.subcommands) == 1
    assert len(ncp.subcommands) == 1
    assert len(tubefeed.subcommands) == 1
