"""Controller group for Nutrition Care Process commands."""

from __future__ import annotations

import typing

from engine.controllers.base import BaseControllerGroup
from engine.controllers.ncp.generate import NCPGenerateController
from engine.controllers.ncp.ingest import NCPIngestController
from engine.controllers.ncp.search import NCPVectorSearchController
from engine.controllers.registry import register_command_group


@register_command_group
class NCPControllerGroup(BaseControllerGroup):
    """Expose local Nutrition Care Process commands."""

    name = "ncp"
    help = "Generate, ingest and search Nutrition Care Process notes"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            NCPGenerateController(),
            NCPIngestController(),
            NCPVectorSearchController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``ncp``."""
        return self._subcommands
