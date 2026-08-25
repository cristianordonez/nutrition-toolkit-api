"""Controller group for all commands under tubefeed."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group
from ntk.controllers.tubefeed.calculate import CalculateTubefeedController

logger = logging.getLogger(__name__)


@register_command_group
class TubefeedControllerGroup(BaseControllerGroup):
    """Controller group for tubefeed command. Holds all subcommands."""

    name = "tubefeed"
    help = "Tubefeed controller group"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [CalculateTubefeedController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Holds children commands.

        :return: list of BaseController subclasses.
        """
        return self._subcommands
