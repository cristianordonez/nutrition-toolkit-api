"""Controller group for resident data commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group
from ntk.controllers.resident.extract import ResidentExtractController


@register_command_group
class ResidentControllerGroup(BaseControllerGroup):
    """Expose resident data extraction commands."""

    name = "resident"
    help = "Extract structured resident data"

    def __init__(self) -> None:
        """Initialize the resident subcommands."""
        self._subcommands = [ResidentExtractController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``resident``."""
        return self._subcommands
