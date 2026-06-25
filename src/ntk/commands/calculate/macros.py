from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ntk.commands.base import BaseCommand
from ntk.models.macros_model import MacrosModel

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)


class MacrosSubCommand(BaseCommand):
    name = "macros"
    help = "macros subcommand"
    options = MacrosModel

    def run(self, args: argparse.Namespace) -> int:
        logger.info("Calculating macronutrient needs")
        return 0
