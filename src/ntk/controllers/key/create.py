from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.key.base import APIKeyController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

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


class CreateController(APIKeyController):
    """Controller for creating new API token."""

    name = "create"
    help = "Create API key"
    options_model = CreateKeyOptions

    def run(self, options: CreateKeyOptions) -> Output:
        """Run Create workflow.

        :param options: pydantic basemodel instance holding options
        :return: Output model
        """
        with self.service() as service:
            plaintext_key = service.create(options.name, options.permissions)
        response = CreateKeyResponse(
            plaintext_key=plaintext_key,
            api_key_name=options.name,
            api_key_permissions=options.permissions,
        )
        return Output(result=response, controller=self.name, exit_code=0)
