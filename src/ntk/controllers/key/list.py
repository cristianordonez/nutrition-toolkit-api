from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.key.base import APIKeyController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.api_key import APIKey  # noqa: TC001

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


class ListController(APIKeyController):
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
        with self.service() as service:
            api_keys = service.get_api_keys(plaintext_key=options.api_key)
        results = ListResponse(api_keys=api_keys)
        return Output(result=results, controller=self.name, exit_code=0)
