"""Create Controller handles creating new api tokens."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.base import CustomBaseSettings
from ntk.models.output import Output
from ntk.repositories.api_key import ApiKeyRepository
from ntk.repositories.permission import PermissionRepository
from ntk.services.api_key import ApiKeyService

logger = logging.getLogger(__name__)


class CreateKeyOptions(CustomBaseSettings):
    """Settings for create controller."""

    permissions: list[str] = Field(description="List of permissions to give API key")
    name: str


class CreateKeyResponse(BaseModel):
    key: str
    name: str
    permissions: list[str]


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
        repo = ApiKeyRepository(session)
        permission_repo = PermissionRepository(session)
        service = ApiKeyService(repo)
        permissions = permission_repo.get_by_names(options.permissions)
        logger.debug("Matching Permissions: %s", permissions)
        if len(permissions) == 0:
            msg = f"Provided permissions not found in database: {options.permissions}"
            raise ValueError(msg)
        api_key = service.create(options, permissions)
        response = CreateKeyResponse(
            key=api_key,
            name=options.name,
            permissions=options.permissions,
        )
        return Output(result=response, controller=self.name, exit_code=0)
