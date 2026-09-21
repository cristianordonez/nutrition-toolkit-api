"""Report whether on-device extraction is ready on this machine."""

from __future__ import annotations

from pydantic import BaseModel

from engine.clients.ollama_client import OllamaClient
from engine.models.settings import SETTINGS
from engine.services.local_model import (
    UnsupportedMachineError,
    recommended_tier,
    resolve_model,
    total_ram_gb,
)
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output


class LocalModelStatusOptions(BaseModel):
    """No options; status always describes this machine."""


class LocalModelStatusResult(ConsoleRenderableModel):
    """Everything the app needs to decide what to show or download."""

    enabled: bool
    ram_gb: int
    supported: bool
    model: str | None
    approximate_download_gb: float | None
    ollama_running: bool
    model_downloaded: bool
    detail: str | None = None

    def to_console(self) -> str:
        """Render the status as formatted JSON."""
        return self.model_dump_json(indent=2)


class LocalModelStatusController(BaseController):
    """Describe on-device extraction readiness."""

    name = "status"
    help = "Report on-device extraction readiness for this machine"
    options_model = LocalModelStatusOptions

    def __init__(self, client: OllamaClient | None = None) -> None:
        """Store the Ollama client used for daemon and model checks."""
        self.client = client or OllamaClient(SETTINGS.ollama_host)

    async def run(
        self,
        options: LocalModelStatusOptions,
    ) -> Output[LocalModelStatusResult]:
        """Return what this machine can run and what it already has."""
        del options
        ram_gb = total_ram_gb()
        try:
            model: str | None = resolve_model(override=SETTINGS.ollama_model)
            supported = True
            detail = None
        except UnsupportedMachineError as error:
            model = None
            supported = False
            detail = str(error)

        running = await self.client.is_available()
        downloaded = bool(
            running and model and await self.client.has_model(model),
        )
        tier = recommended_tier(ram_gb)
        return Output(
            result=LocalModelStatusResult(
                enabled=SETTINGS.use_local_extraction,
                ram_gb=ram_gb,
                supported=supported,
                model=model,
                approximate_download_gb=tier.approximate_download_gb if tier else None,
                ollama_running=running,
                model_downloaded=downloaded,
                detail=detail,
            ),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "LocalModelStatusController",
    "LocalModelStatusOptions",
    "LocalModelStatusResult",
]
