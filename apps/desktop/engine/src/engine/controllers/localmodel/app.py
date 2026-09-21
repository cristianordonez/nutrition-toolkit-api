"""Controller group for on-device model commands."""

from __future__ import annotations

import typing

from engine.controllers.localmodel.ensure import LocalModelEnsureController
from engine.controllers.localmodel.status import LocalModelStatusController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group


@register_command_group
class LocalModelControllerGroup(BaseControllerGroup):
    """Expose on-device extraction model commands."""

    name = "localmodel"
    help = "Manage the on-device extraction model"

    def __init__(self) -> None:
        """Initialize the local-model subcommands."""
        self._subcommands = [
            LocalModelStatusController(),
            LocalModelEnsureController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``localmodel``."""
        return self._subcommands
