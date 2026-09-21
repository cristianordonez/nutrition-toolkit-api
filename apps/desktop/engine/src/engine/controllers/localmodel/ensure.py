"""Download the on-device extraction model when it is missing."""

from __future__ import annotations

import sys

from pydantic import BaseModel

from engine.clients.ollama_client import OllamaClient, OllamaUnavailableError
from engine.models.settings import SETTINGS
from engine.services.local_model import UnsupportedMachineError, resolve_model
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output


class LocalModelEnsureOptions(BaseModel):
    """No options; the model is chosen for this machine."""


class LocalModelEnsureResult(ConsoleRenderableModel):
    """What ensuring the model did."""

    model: str
    downloaded: bool
    already_present: bool

    def to_console(self) -> str:
        """Render the outcome as formatted JSON."""
        return self.model_dump_json(indent=2)


class LocalModelEnsureController(BaseController):
    """Pull the on-device model if this machine does not have it yet."""

    name = "ensure"
    help = "Download the on-device extraction model if it is missing"
    options_model = LocalModelEnsureOptions

    def __init__(self, client: OllamaClient | None = None) -> None:
        """Store the Ollama client used to check for and pull the model."""
        self.client = client or OllamaClient(SETTINGS.ollama_host)

    async def run(
        self,
        options: LocalModelEnsureOptions,
    ) -> Output[LocalModelEnsureResult]:
        """Download the resolved model unless it is already present."""
        del options
        try:
            model = resolve_model(override=SETTINGS.ollama_model)
        except UnsupportedMachineError as error:
            raise OllamaUnavailableError(str(error)) from error

        if await self.client.has_model(model):
            return self._output(model, downloaded=False, already_present=True)

        # A multi-gigabyte pull needs some sign of life. stdout is reserved for
        # the result JSON, so progress goes to stderr.
        await self.client.pull(model, on_progress=_write_progress)
        return self._output(model, downloaded=True, already_present=False)

    def _output(
        self,
        model: str,
        *,
        downloaded: bool,
        already_present: bool,
    ) -> Output[LocalModelEnsureResult]:
        return Output(
            result=LocalModelEnsureResult(
                model=model,
                downloaded=downloaded,
                already_present=already_present,
            ),
            controller=self.name,
            exit_code=0,
        )


def _write_progress(status: str, completed: int, total: int) -> None:
    """Print one progress line to stderr."""
    if total:
        percent = completed / total * 100
        line = f"{status}: {percent:5.1f}% ({completed / 1024**3:.1f}/"
        line += f"{total / 1024**3:.1f} GB)"
    else:
        line = status
    print(line, file=sys.stderr, flush=True)  # noqa: T201


__all__ = [
    "LocalModelEnsureController",
    "LocalModelEnsureOptions",
    "LocalModelEnsureResult",
]
