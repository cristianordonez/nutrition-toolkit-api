"""Report the device user's own settings."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from engine.controllers.base import BaseController
from engine.database.sessions import settings_session
from engine.models.base import ConsoleRenderableModel
from engine.models.output import Output
from engine.models.sql.settings import ApplicationSettings  # noqa: TC001
from engine.repositories.settings_repo import SettingsRepo
from engine.services.credentials import has_cloud_token

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class SettingsShowOptions(BaseModel):
    """Options for reading the user's settings."""


class SettingsResult(ConsoleRenderableModel):
    """The single user-settings row, plus derived state it does not store."""

    settings: ApplicationSettings
    #: Whether an API token is in the OS keychain. The token itself is never
    #: returned: this output crosses a subprocess boundary and is logged.
    has_cloud_token: bool = False

    def to_console(self) -> str:
        """Render the settings as formatted JSON."""
        return self.model_dump_json(indent=2)


class SettingsShowController(BaseController):
    """Return the device user's settings, creating defaults when absent."""

    name = "show"
    help = "Show the current user settings"
    options_model = SettingsShowOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned settings session."""
        self.session = session

    def run(self, options: SettingsShowOptions) -> Output[SettingsResult]:
        """Return the persisted settings row."""
        del options
        with settings_session(self.session) as session:
            stored = SettingsRepo(session).get()
        return Output(
            result=SettingsResult(
                settings=stored,
                has_cloud_token=has_cloud_token(),
            ),
            controller=self.name,
            exit_code=0,
        )


__all__ = ["SettingsResult", "SettingsShowController", "SettingsShowOptions"]
