from __future__ import annotations

import logging

from pydantic import Field

from ntk.controllers.base import BaseController
from ntk.models.base import CustomBaseSettings
from ntk.models.output import Output

logger = logging.getLogger(__name__)


class RevokeOptions(CustomBaseSettings):
    """Options for Rm workflow."""

    energy_needs: tuple[int, int] | None = Field(
        description="Manually set kcal range",
        default=None,
    )


class RevokeController(BaseController):
    """Handles revoking API keys."""

    name = "revoke"
    help = "Revoke API token key"
    options_model = RevokeOptions

    def run(self, options: RevokeOptions) -> Output:
        """Run revoke workflow.

        :param options: pydantic basemodel TubefeedOptions instance
        :return: Output model
        """
        try:
            results = {}
            logger.debug("Options: %s", options)
            ec = 0
        except ValueError:
            ec = 1
        return Output(controller=self.name, exit_code=ec, result=results)
