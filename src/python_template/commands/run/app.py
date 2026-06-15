"""Run build command"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from python_template.commands.base import BaseCommandGroup
from python_template.commands.registry import register_command
from python_template.commands.run.run_test import RunTestSubCommand

if TYPE_CHECKING:
    import logging

    from python_template.commands.base import BaseCommand

logger = logging.getLogger(__name__)


@register_command()
class RunCommandGroup(BaseCommandGroup):
    name = "run"
    help = "Run command group"

    subcommands: list[BaseCommand] = [RunTestSubCommand()]
