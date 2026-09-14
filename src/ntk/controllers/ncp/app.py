"""Controller group for all commands under ncp."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.ncp.finalize import (
    NCPFinalizeCommandController,
)
from ntk.controllers.ncp.get import NCPGetCommandController
from ntk.controllers.ncp.import_ncps import NCPImportController
from ntk.controllers.ncp.search import NCPSearchController
from ntk.controllers.registry import register_command_group

logger = logging.getLogger(__name__)


@register_command_group
class NCPControllerGroup(BaseControllerGroup):
    """Expose ncp management commands."""

    name = "ncp"
    help = "Manage Nutrition Care Processes"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            NCPFinalizeCommandController(),
            NCPGetCommandController(),
            NCPImportController(),
            NCPSearchController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``ncp``."""
        return self._subcommands
