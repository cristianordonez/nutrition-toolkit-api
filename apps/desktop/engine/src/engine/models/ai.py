"""Where inference runs, and whether it can run right now.

These describe data only. Which provider answers is decided in
``engine.services.ai.controller``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class AIProvider(StrEnum):
    """Where a clinical prompt is sent for inference."""

    #: A llama.cpp server on this machine, reached over localhost.
    LOCAL = "local"
    #: OpenAI's hosted API, with the user's own token.
    OPENAI = "openai"


class AIStatusValue(StrEnum):
    """Whether the selected provider can answer now."""

    READY = "ready"
    #: Configured, but not answering (e.g. the local server is down).
    UNAVAILABLE = "unavailable"
    #: Missing configuration (e.g. OpenAI selected with no token stored).
    NOT_CONFIGURED = "not_configured"


class AIStatus(BaseModel):
    """What the Settings screen shows about the selected provider.

    Carries no URL, port, key, file path, prompt or response.
    """

    provider: AIProvider
    status: AIStatusValue
    #: The model answering, when known -- a file name or alias, never a path.
    model: str | None = None
    #: A user-facing sentence, never raw transport detail.
    error: str | None = None


__all__ = ["AIProvider", "AIStatus", "AIStatusValue"]
