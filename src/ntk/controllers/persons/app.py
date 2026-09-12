"""Controller group for person data commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.persons.assessments import PersonAssessmentsController
from ntk.controllers.persons.weights import PersonWeightsController
from ntk.controllers.registry import register_command_group


@register_command_group
class PersonControllerGroup(BaseControllerGroup):
    """Expose person data extraction commands."""

    name = "persons"
    help = "Manage person data"

    def __init__(self) -> None:
        """Initialize the person subcommands."""
        self._subcommands = [
            PersonAssessmentsController(),
            PersonWeightsController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``person``."""
        return self._subcommands
