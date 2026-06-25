"""Run build command"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.calculate.macros import MacrosController
from ntk.controllers.registry import register_command

if TYPE_CHECKING:
    from ntk.controllers.base import BaseController

logger = logging.getLogger(__name__)


@register_command()
class CalculateControllerGroup(BaseControllerGroup):
    name = "calculate"
    help = "Calculate controller group"

    subcommands: list[BaseController] = [MacrosController()]
