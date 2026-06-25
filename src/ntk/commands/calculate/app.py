"""Run build command"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ntk.commands.base import BaseCommandGroup
from ntk.commands.calculate.macros import MacrosSubCommand
from ntk.commands.registry import register_command

if TYPE_CHECKING:
    from ntk.commands.base import BaseCommand

logger = logging.getLogger(__name__)


@register_command()
class CalculateCommandGroup(BaseCommandGroup):
    name = "calculate"
    help = "Calculate command group"

    subcommands: list[BaseCommand] = [MacrosSubCommand()]
