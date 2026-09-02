"""Controller group for resident data commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group
from ntk.controllers.residents.assessments import ResidentAssessmentsController
from ntk.controllers.residents.weights import ResidentWeightsController


@register_command_group
class ResidentControllerGroup(BaseControllerGroup):
    """Expose resident data extraction commands."""

    name = "residents"
    help = "Manage resident data"

    def __init__(self) -> None:
        """Initialize the resident subcommands."""
        self._subcommands = [
            ResidentAssessmentsController(),
            ResidentWeightsController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``resident``."""
        return self._subcommands
