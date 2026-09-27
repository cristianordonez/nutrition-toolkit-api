"""Controller group for ad hoc calculators."""

from __future__ import annotations

import typing

from engine.controllers.base import BaseControllerGroup
from engine.controllers.calculate.energy import EnergyController
from engine.controllers.registry import register_command_group


@register_command_group
class CalculateControllerGroup(BaseControllerGroup):
    """Expose ad hoc calculation commands."""

    name = "calculate"
    help = "Ad hoc nutrition calculators"

    def __init__(self) -> None:
        """Initialize the calculator subcommands."""
        self._subcommands = [EnergyController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``calculate``."""
        return self._subcommands
