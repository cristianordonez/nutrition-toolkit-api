"""Controller group for local clinical-note-report import commands."""

from __future__ import annotations

import logging
import typing

from engine.controllers.ncp.generate import NCPGenerateController
from engine.controllers.ncp.import_ncps import NCPImportController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group

logger = logging.getLogger(__name__)


@register_command_group
class NCPControllerGroup(BaseControllerGroup):
    """Expose local Nutrition Care Process import commands."""

    name = "ncp"
    help = "Import clinical-note reports"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            NCPGenerateController(),
            NCPImportController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``ncp``."""
        return self._subcommands
