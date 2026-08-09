"""Controller group for all commands under key."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.key.create import CreateController
from ntk.controllers.key.list import ListController
from ntk.controllers.key.revoke import RevokeController
from ntk.controllers.registry import register_command

logger = logging.getLogger(__name__)


@register_command()
class KeyControllerGroup(BaseControllerGroup):
    """Controller group for key command. Holds logic for handling api key."""

    name = "key"
    help = "API Key controller group"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [CreateController(), ListController(), RevokeController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Holds children commands.

        :return: list of BaseController subclasses.
        """
        return self._subcommands
