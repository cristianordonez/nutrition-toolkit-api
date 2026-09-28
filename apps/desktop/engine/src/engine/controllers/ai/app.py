"""Controller group for AI provider status and checks."""

from __future__ import annotations

import typing

from engine.controllers.ai.check import AICheckController
from engine.controllers.ai.status import AIStatusController
from engine.controllers.base import BaseControllerGroup
from engine.controllers.registry import register_command_group


@register_command_group
class AIControllerGroup(BaseControllerGroup):
    """Expose AI provider commands."""

    name = "ai"
    help = "Check the selected AI provider"

    def __init__(self) -> None:
        """Initialize the ai subcommands."""
        self._subcommands = [AIStatusController(), AICheckController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``ai``."""
        return self._subcommands
