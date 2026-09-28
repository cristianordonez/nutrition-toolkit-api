"""OpenAI: hosted models, used only when the user selects it with a token.

The token is the user's own and lives in the OS keychain
(``engine.services.credentials``), never in SQLite. Structured output uses
OpenAI's own support through pydantic-ai; nothing here is llama.cpp-specific.
"""

from __future__ import annotations

import typing

from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider as OpenAICompatibleProvider

from engine.models.ai import AIProvider, AIStatus, AIStatusValue
from engine.services.ai.boundary import ProviderErrorBoundary
from engine.services.ai.errors import (
    OpenAIConfigurationError,
    OpenAITimeoutError,
    OpenAIUnavailableError,
)
from engine.services.credentials import get_cloud_token

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic_ai.models import Model

#: The hosted model every task uses.
CLOUD_MODEL = "gpt-5.6-luna"
_NO_TOKEN = "OpenAI is selected but no API token is stored."  # noqa: S105 - a message


class OpenAIProvider:
    """OpenAI's hosted models, with the user's own token."""

    kind = AIProvider.OPENAI

    def __init__(self, token: Callable[[], str | None] | None = None) -> None:
        """Read the token when needed, so a newly stored one is picked up.

        ``token`` replaces the keychain lookup (tests).
        """
        self._read_token = token

    def _token(self) -> str | None:
        return (self._read_token or get_cloud_token)()

    def model(self) -> Model:
        """Return the hosted model; refuse to run without a token."""
        token = self._token()
        if not token:
            raise OpenAIConfigurationError(_NO_TOKEN)
        return ProviderErrorBoundary(
            OpenAIResponsesModel(
                CLOUD_MODEL,
                provider=OpenAICompatibleProvider(api_key=token),
            ),
            label="OpenAI",
            recorded_name=f"{AIProvider.OPENAI.value}:{CLOUD_MODEL}",
            unavailable=OpenAIUnavailableError,
            timeout=OpenAITimeoutError,
        )

    async def health(self) -> AIStatus:
        """Report whether a token is stored; no request is sent to OpenAI."""
        if self._token():
            return AIStatus(
                provider=self.kind,
                status=AIStatusValue.READY,
                model=CLOUD_MODEL,
            )
        return AIStatus(
            provider=self.kind,
            status=AIStatusValue.NOT_CONFIGURED,
            error=_NO_TOKEN,
        )


__all__ = ["CLOUD_MODEL", "OpenAIProvider"]
