"""Shared API-key controller session boundary."""

from __future__ import annotations

import typing
from contextlib import contextmanager

from api.controllers.session import controller_session
from api.repositories.api_key_repo import APIKeyRepo
from api.repositories.permission_repo import PermissionRepo
from api.services.api_key_service import APIKeyService
from ntk.controllers.base import BaseController

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlmodel import Session


class APIKeyController(BaseController):
    """Give API-key controllers one optional controller-owned session."""

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional externally managed session."""
        self.session = session

    @contextmanager
    def service(self) -> Iterator[APIKeyService]:
        """Build a repository-only service within the controller session."""
        with controller_session(self.session) as session:
            yield APIKeyService(APIKeyRepo(session), PermissionRepo(session))
