"""List Controller handles listing API tokens."""

from __future__ import annotations

import logging

from pydantic import Field

from ntk.controllers.base import BaseController
from ntk.models.base import CustomBaseSettings
from ntk.models.output import Output

logger = logging.getLogger(__name__)


class ListOptions(CustomBaseSettings):
    """Settings for list controller."""

    weight: float = Field(description="Weight in lbs")
    height: int = Field(description="Height in inches")


class ListController(BaseController):
    """Controller for calculating energy needs."""

    name = "list"
    help = "List API tokens"
    options_model = ListOptions

    def run(self, options: ListOptions) -> Output:
        """Run Energy workflow.

        :param options: pydantic basemodel instance holding options
        :return: Output model
        """
        results = {}
        logger.debug(options)
        return Output(result=results, controller=self.name, exit_code=0)
