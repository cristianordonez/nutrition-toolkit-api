from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ntk.controllers.base import BaseController
from ntk.models.macros_model import MacrosModel

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)


class MacrosController(BaseController):
    name = "macros"
    help = "macros command"
    options = MacrosModel

    def run(self, args: argparse.Namespace) -> int:
        logger.info("Calculating macronutrient needs")
        print("args: ", args)
        return 0
