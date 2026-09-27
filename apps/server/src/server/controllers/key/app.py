"""Controller group for all commands under key."""

from __future__ import annotations

import logging
import typing

from server.controllers.base import BaseControllerGroup
from server.controllers.registry import register_command_group
from server.controllers.key.create import CreateController
from server.controllers.key.grant import GrantPermissionsController
from server.controllers.key.list import ListController
from server.controllers.key.revoke import RevokeController
from server.controllers.key.revoke_permission import RevokePermissionsController

logger = logging.getLogger(__name__)


@register_command_group
class KeyControllerGroup(BaseControllerGroup):
    """Controller group for key command. Holds logic for handling api key."""

    name = "key"
    help = "API Key controller group"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            CreateController(),
            ListController(),
            RevokeController(),
            GrantPermissionsController(),
            RevokePermissionsController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Holds children commands.

        :return: list of BaseController subclasses.
        """
        return self._subcommands
