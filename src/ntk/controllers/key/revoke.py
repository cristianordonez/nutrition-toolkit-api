from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.key.base import APIKeyController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.api_key import APIKey  # noqa: TC001

logger = logging.getLogger(__name__)


class RevokeOptions(BaseModel):
    """Options for Rm workflow."""

    api_key: str = Field(
        description="Plaintext API key to filter by",
    )


class RevokeResponse(ConsoleRenderableModel):
    """Response for Rm workflow."""

    revoked_key: APIKey | None = Field(
        description="Revoked API key model or None if not found",
        default=None,
    )

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        if self.revoked_key is None:
            return "No API key found to revoke."
        return f"Key revoked: {self.revoked_key}"


class RevokeController(APIKeyController):
    """Handles revoking API keys."""

    name = "revoke"
    help = "Revoke API token key"
    options_model = RevokeOptions

    def run(self, options: RevokeOptions) -> Output:
        """Run revoke workflow.

        :param options: pydantic basemodel TubefeedOptions instance
        :return: Output model
        """
        results = RevokeResponse(revoked_key=None)
        try:
            logger.debug(options)
            with self.service() as service:
                revoked_key = service.revoke_api_key(options.api_key)
            results.revoked_key = revoked_key
            ec = 0
        except ValueError:
            logger.exception("Error revoking API key")
            ec = 1
        return Output(controller=self.name, exit_code=ec, result=results)
