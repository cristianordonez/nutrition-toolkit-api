from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.api_key import ApiKey  # noqa: TC001
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.repositories.api_key import ApiKeyRepository
from ntk.repositories.permission import PermissionRepository
from ntk.services.api_key import ApiKeyService

logger = logging.getLogger(__name__)


class RevokeOptions(BaseModel):
    """Options for Rm workflow."""

    api_key: str = Field(
        description="Plaintext API key to filter by",
    )


class RevokeResponse(ConsoleRenderableModel):
    """Response for Rm workflow."""

    revoked_key: ApiKey | None = Field(
        description="Revoked API key model or None if not found",
        default=None,
    )

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        if self.revoked_key is None:
            return "No API key found to revoke."
        return f"Key revoked: {self.revoked_key}"


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
            logger.debug(options)
            session = next(get_session())
            repo = ApiKeyRepository(session)
            permission_repo = PermissionRepository(session)
            service = ApiKeyService(repo, permission_repo)
            revoked_key = service.revoke_api_key(options.api_key)
            results = RevokeResponse(revoked_key=revoked_key)
            ec = 0
        except ValueError:
            ec = 1
        return Output(controller=self.name, exit_code=ec, result=results)
