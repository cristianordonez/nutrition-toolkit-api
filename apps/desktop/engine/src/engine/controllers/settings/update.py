"""Change the device user's own settings."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.controllers.settings.show import SettingsResult
from engine.database.sessions import settings_session
from engine.models.ai import AIProvider  # noqa: TC001 - Pydantic field type
from engine.models.output import Output
from engine.repositories.settings_repo import SettingsRepo
from engine.services.credentials import has_cloud_token, set_cloud_token

if typing.TYPE_CHECKING:
    from sqlmodel import Session

#: What the caller may pass for ``--dark-mode``. A plain bool would become an
#: argparse ``store_true`` flag, which can turn the setting on but never off,
#: so the three states are spelled out instead.
DarkMode = typing.Literal["on", "off", "system"]

_DARK_MODE_VALUES: dict[str, bool | None] = {
    "on": True,
    "off": False,
    "system": None,
}


class SettingsUpdateOptions(BaseModel):
    """The settings to change. Anything left unset is untouched."""

    dark_mode: DarkMode | None = Field(
        default=None,
        description="Force dark ('on'), force light ('off'), or follow the OS",
    )
    ai_provider: AIProvider | None = Field(
        default=None,
        description=(
            "Where inference runs: 'local' (llama.cpp on this machine) "
            "or 'openai' (hosted, with your own API token)"
        ),
    )
    cloud_api_token: str | None = Field(
        default=None,
        description=(
            "Your own API token, stored in the OS keychain. Pass an empty "
            "string to remove it."
        ),
    )


class SettingsUpdateController(BaseController):
    """Apply changes to the device user's settings."""

    name = "update"
    help = "Change user settings"
    options_model = SettingsUpdateOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned settings session."""
        self.session = session

    def run(self, options: SettingsUpdateOptions) -> Output[SettingsResult]:
        """Apply the requested changes and return the whole settings row."""
        changes: dict[str, object] = {}
        if options.dark_mode is not None:
            changes["dark_mode"] = _DARK_MODE_VALUES[options.dark_mode]
        if options.ai_provider is not None:
            changes["ai_provider"] = options.ai_provider

        # The token never reaches SQLite -- it goes to the OS keychain,
        # and only a boolean "is one stored" is ever reported back.
        if options.cloud_api_token is not None:
            set_cloud_token(options.cloud_api_token)

        with settings_session(self.session) as session:
            repository = SettingsRepo(session)
            # An empty update is not an error: the caller still gets the
            # current row back, which is what a "save" with nothing changed
            # should do.
            stored = repository.update(**changes) if changes else repository.get()
        return Output(
            result=SettingsResult(
                settings=stored,
                has_cloud_token=has_cloud_token(),
            ),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "DarkMode",
    "SettingsUpdateController",
    "SettingsUpdateOptions",
]
