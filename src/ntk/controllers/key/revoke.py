from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

logger = logging.getLogger(__name__)


class RevokeOptions(BaseModel):
    """Options for Rm workflow."""

    energy_needs: tuple[int, int] | None = Field(
        description="Manually set kcal range",
        default=None,
    )


class RevokeResponse(ConsoleRenderableModel):
    """Response for Rm workflow."""

    energy_needs: tuple[int, int] | None = Field(
        description="Manually set kcal range",
        default=None,
    )

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        return f"Energy Needs: {self.energy_needs}"


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
            results = RevokeResponse(energy_needs=(2000, 2500))
            logger.debug("Options: %s", options)
            ec = 0
        except ValueError:
            ec = 1
        return Output(controller=self.name, exit_code=ec, result=results)
