"""Talk to a local Ollama daemon about models.

Only the model-management endpoints live here. Inference itself goes through
pydantic-ai's ``OllamaProvider`` in the extraction agent, which speaks the
OpenAI-compatible API on the same host.

Ollama is a separate application that the desktop app cannot install silently,
so every call here has to tolerate it being absent and say so plainly rather
than raising a connection error at the UI.
"""

from __future__ import annotations

import json
import typing

import httpx

DEFAULT_HOST = "http://localhost:11434"


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama daemon cannot be reached."""


class OllamaClient:
    """Query and pull models on a local Ollama daemon."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        *,
        timeout: float = 10.0,
        pull_timeout: float = 3600.0,
    ) -> None:
        """Store the daemon host and the per-request timeouts."""
        self._host = host.rstrip("/")
        self._timeout = timeout
        # Pulling is measured in gigabytes, so it gets its own long timeout.
        self._pull_timeout = pull_timeout

    async def is_available(self) -> bool:
        """Report whether the daemon answers, without raising."""
        try:
            await self.list_models()
        except OllamaUnavailableError:
            return False
        return True

    async def list_models(self) -> list[str]:
        """Return the model names this daemon already has downloaded."""
        payload = await self._get("/api/tags")
        models = payload.get("models", [])
        return [str(model["name"]) for model in models if "name" in model]

    async def has_model(self, model: str) -> bool:
        """Report whether a model is already downloaded.

        Ollama reports tagged names (``qwen2.5:14b``), and a bare name means
        the ``latest`` tag, so compare both spellings.
        """
        wanted = model if ":" in model else f"{model}:latest"
        return wanted in await self.list_models()

    async def pull(
        self,
        model: str,
        on_progress: typing.Callable[[str, int, int], None] | None = None,
    ) -> None:
        """Download a model, reporting progress as it streams.

        ``on_progress`` receives ``(status, completed_bytes, total_bytes)``.
        """
        url = f"{self._host}/api/pull"
        try:
            async with (
                httpx.AsyncClient(timeout=self._pull_timeout) as client,
                client.stream(
                    "POST",
                    url,
                    json={"model": model, "stream": True},
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    self._report(line, on_progress)
        except httpx.HTTPError as error:
            raise OllamaUnavailableError(self._unreachable(error)) from error

    @staticmethod
    def _report(
        line: str,
        on_progress: typing.Callable[[str, int, int], None] | None,
    ) -> None:
        """Forward one streamed progress line, ignoring malformed ones."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if error := event.get("error"):
            raise OllamaUnavailableError(str(error))
        if on_progress is not None:
            on_progress(
                str(event.get("status", "")),
                int(event.get("completed", 0)),
                int(event.get("total", 0)),
            )

    async def _get(self, path: str) -> dict[str, typing.Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._host}{path}")
                response.raise_for_status()
                return dict(response.json())
        except httpx.HTTPError as error:
            raise OllamaUnavailableError(self._unreachable(error)) from error

    def _unreachable(self, error: Exception) -> str:
        return (
            f"Could not reach Ollama at {self._host} ({error}). "
            "Install it from https://ollama.com and make sure it is running."
        )


__all__ = ["DEFAULT_HOST", "OllamaClient", "OllamaUnavailableError"]
