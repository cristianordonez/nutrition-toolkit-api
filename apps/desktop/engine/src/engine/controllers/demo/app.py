"""Controller group for the extract-then-print-context developer workflow."""

from __future__ import annotations

import typing

from engine.controllers.demo.build_context import BuildContextController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group


@register_command_group
class DemoControllerGroup(BaseControllerGroup):
    """Expose the local extract-and-print-context developer command."""

    name = "demo"
    help = "Developer workflow: extract documents, print generation requests"

    def __init__(self) -> None:
        """Initialize demo subcommands."""
        self._subcommands = [BuildContextController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``demo``."""
        return self._subcommands
