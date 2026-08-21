"""Controller group for all commands under assessment."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.calculate.energy import EnergyController
from ntk.controllers.registry import register_command

logger = logging.getLogger(__name__)


@register_command()
class AssessmentControllerGroup(BaseControllerGroup):
    """Controller group for calc command. Holds all subcommands."""

    name = "assessment"
    help = "Assessment controller group"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [EnergyController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``assessment``."""
        return self._subcommands
