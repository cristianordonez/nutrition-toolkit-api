"""Shared API-key controller session boundary."""

from __future__ import annotations

import typing
from contextlib import contextmanager

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.repositories.api_key_repo import APIKeyRepo
from ntk.repositories.permission_repo import PermissionRepo
from ntk.services.api_key_service import APIKeyService

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
