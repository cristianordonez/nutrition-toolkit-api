"""The one place that decides which AI provider handles a request.

Every AI consumer -- the extraction agent, the note agent, the eval and check
commands -- asks ``AIController`` for a model (or a one-off ``chat``) and
never learns which provider answered. The controller only selects:

* ``LOCAL`` -> ``LocalAIProvider`` (llama.cpp on this machine; the default)
* ``OPENAI`` -> ``OpenAIProvider`` (hosted, with the user's own token)

It does not start servers, find models or build prompts. A provider that
fails raises; nothing here retries on the other one. Switching providers is
always the user's explicit choice in Settings.
"""

from __future__ import annotations

import functools
import logging
import typing

from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from sqlalchemy.exc import SQLAlchemyError

from engine.database.sessions import settings_session
from engine.models.ai import AIProvider, AIStatus
from engine.models.settings import LOCAL_AI_SETTINGS
from engine.repositories.settings_repo import SettingsRepo
from engine.services.ai.errors import (
    AIStructuredOutputError,
    UnsupportedAIProviderError,
)
from engine.services.ai.local_provider import LocalAIProvider
from engine.services.ai.openai_provider import OpenAIProvider

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic_ai.models import Model

logger = logging.getLogger(__name__)

OutputT = typing.TypeVar("OutputT")


class LLMProvider(typing.Protocol):
    """What both providers offer the controller."""

    kind: AIProvider

    def model(self) -> Model:
        """Return a pydantic-ai model on this provider."""
        ...

    async def health(self) -> AIStatus:
        """Report whether the provider can answer now, changing nothing."""
        ...


def selected_provider() -> AIProvider:
    """Return the provider the user chose in Settings.

    A settings database that cannot be read means Local AI: on-device is what
    a device with no stored preference should do. It never means OpenAI.
    """
    try:
        with settings_session(None) as session:
            return SettingsRepo(session).get().ai_provider
    except (SQLAlchemyError, OSError, LookupError):
        logger.warning("Could not read user settings", exc_info=True)
        return AIProvider.LOCAL


class AIController:
    """Route each request to the provider the user selected."""

    def __init__(
        self,
        local: LLMProvider,
        openai: LLMProvider,
        selected: Callable[[], AIProvider] = selected_provider,
    ) -> None:
        """Hold both providers and how to read the user's choice."""
        self.local = local
        self.openai = openai
        self._selected = selected

    def provider(self, kind: AIProvider | None = None) -> LLMProvider:
        """Return ``kind``'s provider, or the selected one."""
        kind = kind or self._selected()
        if kind is AIProvider.LOCAL:
            return self.local
        if kind is AIProvider.OPENAI:
            return self.openai
        msg = f"Unsupported AI provider: {kind}"
        raise UnsupportedAIProviderError(msg)

    def model(self, *, provider: AIProvider | None = None) -> Model:
        """Return a model for an agent, on the selected provider.

        ``provider`` overrides the selection only for side-by-side comparisons
        (``eval``).
        """
        return self.provider(provider).model()

    async def health(self, provider: AIProvider | None = None) -> AIStatus:
        """Report whether the selected provider can answer now."""
        return await self.provider(provider).health()

    async def chat(
        self,
        prompt: str,
        *,
        output_type: type[OutputT] = str,  # ty: ignore[invalid-parameter-default]
        instructions: str | None = None,
        provider: AIProvider | None = None,
    ) -> OutputT:
        """Run one prompt; return text or a validated structured object.

        For single requests without tools. Agents with tools build their own
        pydantic-ai ``Agent`` on ``model()``.
        """
        agent = Agent(
            self.model(provider=provider),
            output_type=output_type,
            instructions=instructions,
            retries=1,
        )
        try:
            result = await agent.run(prompt)
        except UnexpectedModelBehavior as error:
            msg = "The AI's answer did not match the expected structure."
            raise AIStructuredOutputError(
                msg,
                diagnostic=type(error).__name__,
            ) from error
        return typing.cast("OutputT", result.output)


@functools.cache
def ai_controller() -> AIController:
    """Return the process's controller, built from the configured settings."""
    return AIController(LocalAIProvider(LOCAL_AI_SETTINGS), OpenAIProvider())


__all__ = ["AIController", "LLMProvider", "ai_controller", "selected_provider"]
