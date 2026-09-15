"""Controller group for all commands under key."""

from __future__ import annotations

import logging
import typing

from api.controllers.key.create import CreateController
from api.controllers.key.grant import GrantPermissionsController
from api.controllers.key.list import ListController
from api.controllers.key.revoke import RevokeController
from api.controllers.key.revoke_permission import RevokePermissionsController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group

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
