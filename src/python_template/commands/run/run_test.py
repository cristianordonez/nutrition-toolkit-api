from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from python_template.commands.base import BaseCommand
from python_template.models.run_test_model import RunTestModel

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)


class RunTestSubCommand(BaseCommand):
    name = "test"
    help = "test subcommand"
    options = RunTestModel

    def run(self, args: argparse.Namespace) -> int:
        logger.info("Run test")
        logger.info(args)
        return 0
