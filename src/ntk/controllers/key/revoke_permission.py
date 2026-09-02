from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.key.base import APIKeyController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

logger = logging.getLogger(__name__)


class RevokePermissionsOptions(BaseModel):
    """Settings for revoke permissions controller."""

    api_key: str = Field(
        description="Plaintext API key to revoke permission for",
    )
    permissions: list[str] = Field(
        description="List of permissions to revoke from API key",
    )


class RevokePermissionsResponse(ConsoleRenderableModel):
    """Response for revoke permissions controller."""

    permissions: list[str] | None = Field(
        description="List of revoked permissions",
        default=None,
    )

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        return f"Revoked permissions: {', '.join(self.permissions or [])}"


class RevokePermissionsController(APIKeyController):
    """Controller for revoking API key permissions."""

    name = "revoke-permissions"
    help = "Revoke permissions from an API key"
    options_model = RevokePermissionsOptions

    def run(self, options: RevokePermissionsOptions) -> Output:
        """Run Revoke Permissions workflow.

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
                service.revoke_permission(api_key, permission)
        results = RevokePermissionsResponse(permissions=options.permissions)
        return Output(result=results, controller=self.name, exit_code=0)
