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


class CreateKeyOptions(BaseModel):
    """Settings for create controller."""

    permissions: list[str] = Field(description="List of permissions to give API key")
    name: str


class CreateKeyResponse(ConsoleRenderableModel):
    plaintext_key: str
    api_key_name: str
    api_key_permissions: list[str]

    def to_console(self) -> str:
        """Return a string representation of the model for console output."""
        return (
            f"API Key Name: {self.api_key_name}\n"
            f"API Key Permissions: {', '.join(self.api_key_permissions)}\n"
            f"Plaintext API Key (use this to authenticate): {self.plaintext_key}"
        )


class CreateController(BaseController):
    """Controller for creating new API token."""

    name = "create"
    help = "Create API key"
    options_model = CreateKeyOptions

    def run(self, options: CreateKeyOptions) -> Output:
        """Run Create workflow.

        :param options: pydantic basemodel instance holding options
        :return: Output model
        """
        session = next(get_session())
        repo = APIKeyRepo(session)
        permission_repo = PermissionRepo(session)
        service = APIKeyService(repo, permission_repo)
        plaintext_key = service.create(options.name, options.permissions)
        response = CreateKeyResponse(
            plaintext_key=plaintext_key,
            api_key_name=options.name,
            api_key_permissions=options.permissions,
        )
        return Output(result=response, controller=self.name, exit_code=0)
