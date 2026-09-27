"""Controller group for extraction evaluation commands."""

from __future__ import annotations

import typing

from engine.controllers.base import BaseControllerGroup
from engine.controllers.eval.extraction import EvalExtractionController
from engine.controllers.registry import register_command_group


@register_command_group
class EvalControllerGroup(BaseControllerGroup):
    """Expose extraction evaluation commands."""

    name = "eval"
    help = "Compare extraction providers"

    def __init__(self) -> None:
        """Initialize the eval subcommands."""
        self._subcommands = [EvalExtractionController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``eval``."""
        return self._subcommands
