"""Controller group for all commands under Calc."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.calculate.energy import EnergyController
from ntk.controllers.registry import register_command

logger = logging.getLogger(__name__)


@register_command()
class CalculateControllerGroup(BaseControllerGroup):
    """Controller group for calc command. Holds all subcommands."""

    name = "calc"
    help = "Calculate controller group"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [EnergyController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Holds children commands.

        :return: list of BaseController subclasses.
        """
        return self._subcommands
