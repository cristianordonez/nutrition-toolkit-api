from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.key.base import APIKeyController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

logger = logging.getLogger(__name__)


class GrantOptions(BaseModel):
    """Settings for grant controller."""

    api_key: str = Field(
        description="Plaintext API key to grant permission for",
    )
    permissions: list[str] = Field(
        description="List of permissions to grant to API key",
    )


class GrantResponse(ConsoleRenderableModel):
    """Response for grant controller."""

    permissions: list[str] | None = Field(
        description="List of granted permissions",
        default=None,
    )

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        return f"Granted permissions: {', '.join(self.permissions or [])}"


class GrantPermissionsController(APIKeyController):
    """Controller for granting API key permissions."""

    name = "grant-permissions"
    help = "Grant permissions to an API key"
    options_model = GrantOptions

    def run(self, options: GrantOptions) -> Output:
        """Run Grant Permissions workflow.

        :param options: pydantic basemodel instance holding options
        :return: Output model
        """
        logger.debug(options)
        with self.service() as service:
            api_keys = service.get_api_keys(plaintext_key=options.api_key)
            if len(api_keys) == 0:
                msg = f"No API key found for '{options.api_key}'"
                logger.error(msg)
                raise ValueError(msg)
            api_key = api_keys[0]
            for permission in options.permissions:
                service.grant_permission(api_key, permission)
        results = GrantResponse(permissions=options.permissions)
        return Output(result=results, controller=self.name, exit_code=0)
