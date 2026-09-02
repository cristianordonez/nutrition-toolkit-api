"""Controller group for food data."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group


@register_command_group
class FoodControllerGroup(BaseControllerGroup):
    """Expose food related commands."""

    name = "food"
    help = "Manage details around food."

    def __init__(self) -> None:
        """Initialize the food subcommands."""
        self._subcommands = []

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``knowledge``."""
        return self._subcommands
