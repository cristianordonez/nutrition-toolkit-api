from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.repositories.api_key_repo import APIKeyRepo
from ntk.repositories.permission_repo import PermissionRepo
from ntk.services.api_key_service import APIKeyService

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


class RevokePermissionsController(BaseController):
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
        session = next(get_session())
        repo = APIKeyRepo(session)
        permission_repo = PermissionRepo(session)
        service = APIKeyService(repo, permission_repo)
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
