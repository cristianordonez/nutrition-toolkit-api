"""Controller group for all commands under settings."""

from __future__ import annotations

import typing

from engine.controllers.base import BaseControllerGroup
from engine.controllers.registry import register_command_group
from engine.controllers.settings.show import SettingsShowController
from engine.controllers.settings.update import SettingsUpdateController


@register_command_group
class SettingsControllerGroup(BaseControllerGroup):
    """Controller group for settings commands. Holds all subcommands."""

    name = "settings"
    help = "Read and change the device user's own settings"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            SettingsShowController(),
            SettingsUpdateController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Holds children commands.

        :return: list of BaseController subclasses.
        """
        return self._subcommands
