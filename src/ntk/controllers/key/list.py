from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.api_key import APIKey  # noqa: TC001
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.repositories.api_key_repo import APIKeyRepo
from ntk.repositories.permission_repo import PermissionRepo
from ntk.services.api_key_service import APIKeyService

logger = logging.getLogger(__name__)


class ListOptions(BaseModel):
    """Settings for list controller."""

    api_key: str | None = Field(
        description="Plaintext API key to filter by, if not provided will list all",
        default=None,
    )


class ListResponse(ConsoleRenderableModel):
    """Response for list controller."""

    api_keys: list[APIKey] | None = Field(
        description="List of API keys",
        default=None,
    )

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        result = "API Keys:\n"
        for api_key in self.api_keys or []:
            result += f"  {api_key}\n"
            result += f"  Permissions: {api_key.permissions}"
        return result


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
        logger.debug(options)
        session = next(get_session())
        repo = APIKeyRepo(session)
        permission_repo = PermissionRepo(session)
        service = APIKeyService(repo, permission_repo)
        api_keys = service.get_api_keys(plaintext_key=options.api_key)
        results = ListResponse(api_keys=api_keys)
        return Output(result=results, controller=self.name, exit_code=0)
