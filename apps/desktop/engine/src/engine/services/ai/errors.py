"""Errors an AI provider raises, worded for the person using the app.

``str(error)`` is always safe to show a dietitian and to log: it never holds a
prompt, a completion, a resident's details or raw transport output. What a
developer needs beyond that goes in ``diagnostic`` -- still free of clinical
content -- which is logged, not shown.
"""

from __future__ import annotations


class AIProviderError(RuntimeError):
    """Base for every inference-provider failure."""

    def __init__(self, message: str, *, diagnostic: str | None = None) -> None:
        """Keep the user-facing message apart from developer detail."""
        super().__init__(message)
        self.diagnostic = diagnostic


class ProviderConfigurationError(AIProviderError):
    """The selected provider is not set up to run."""


class UnsupportedAIProviderError(ProviderConfigurationError):
    """A provider value this application does not support."""


class AIProviderUnavailableError(AIProviderError):
    """The selected provider did not answer."""


class AITimeoutError(AIProviderUnavailableError):
    """The selected provider did not answer in time."""


class AIStructuredOutputError(AIProviderError):
    """The model's answer did not fit the requested structure."""


class LocalAIUnavailableError(AIProviderUnavailableError):
    """The local llama.cpp server could not be reached or failed."""


class LocalAITimeoutError(LocalAIUnavailableError, AITimeoutError):
    """The local server did not answer in time."""


class OpenAIUnavailableError(AIProviderUnavailableError):
    """OpenAI could not be reached or refused the request."""


class OpenAITimeoutError(OpenAIUnavailableError, AITimeoutError):
    """OpenAI did not answer in time."""


class OpenAIConfigurationError(ProviderConfigurationError):
    """OpenAI is selected but not set up (no API token stored)."""


__all__ = [
    "AIProviderError",
    "AIProviderUnavailableError",
    "AIStructuredOutputError",
    "AITimeoutError",
    "LocalAITimeoutError",
    "LocalAIUnavailableError",
    "OpenAIConfigurationError",
    "OpenAITimeoutError",
    "OpenAIUnavailableError",
    "ProviderConfigurationError",
    "UnsupportedAIProviderError",
]
