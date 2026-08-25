from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.api_key import APIKey  # noqa: TC001
from ntk.repositories.api_key_repo import APIKeyRepo
from ntk.repositories.permission_repo import PermissionRepo
from ntk.services.api_key_service import APIKeyService

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
        results = RevokeResponse(revoked_key=None)
        try:
            logger.debug(options)
            session = next(get_session())
            repo = APIKeyRepo(session)
            permission_repo = PermissionRepo(session)
            service = APIKeyService(repo, permission_repo)
            revoked_key = service.revoke_api_key(options.api_key)
            results.revoked_key = revoked_key
            ec = 0
        except ValueError:
            logger.exception("Error revoking API key")
            ec = 1
        return Output(controller=self.name, exit_code=ec, result=results)
