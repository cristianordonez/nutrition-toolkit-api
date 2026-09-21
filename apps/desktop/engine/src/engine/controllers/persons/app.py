"""Controller group for person data commands."""

from __future__ import annotations

import typing

from engine.controllers.persons.list import PersonListController
from engine.controllers.persons.ncps import PersonNCPsController
from engine.controllers.persons.weights import PersonWeightsController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group


@register_command_group
class PersonControllerGroup(BaseControllerGroup):
    """Expose person data extraction commands."""

    name = "persons"
    help = "Manage person data"

    def __init__(self) -> None:
        """Initialize the person subcommands."""
        self._subcommands = [
            PersonListController(),
            PersonNCPsController(),
            PersonWeightsController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``person``."""
        return self._subcommands
