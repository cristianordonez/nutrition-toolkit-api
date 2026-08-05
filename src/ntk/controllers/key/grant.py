from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.repositories.api_key import ApiKeyRepository
from ntk.repositories.permission import PermissionRepository
from ntk.services.api_key import ApiKeyService

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


class GrantPermissionsController(BaseController):
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
        session = next(get_session())
        repo = ApiKeyRepository(session)
        permission_repo = PermissionRepository(session)
        service = ApiKeyService(repo, permission_repo)
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
