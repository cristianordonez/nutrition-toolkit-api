"""Report whether the selected AI provider can answer.

Nothing is started or downloaded, and nothing sensitive is returned: no URL,
port, key, file path, prompt or response.
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.controllers.base import BaseController
from engine.models.ai import AIStatus
from engine.models.base import ConsoleRenderableModel
from engine.models.output import Output
from engine.services.ai.controller import AIController, ai_controller


class AIStatusOptions(BaseModel):
    """No options; status describes the provider selected in Settings."""


class AIStatusResult(AIStatus, ConsoleRenderableModel):
    """The selected provider and whether it is ready."""

    def to_console(self) -> str:
        """Render the status as formatted JSON."""
        return self.model_dump_json(indent=2)


class AIStatusController(BaseController):
    """Describe the selected provider's readiness."""

    name = "status"
    help = "Report whether the selected AI provider is ready"
    options_model = AIStatusOptions

    def __init__(self, ai: AIController | None = None) -> None:
        """Store the controller to ask, if injected."""
        self.ai = ai

    async def run(self, options: AIStatusOptions) -> Output[AIStatusResult]:
        """Return the selected provider's status."""
        del options
        status = await (self.ai or ai_controller()).health()
        return Output(
            result=AIStatusResult(**status.model_dump()),
            controller=self.name,
            exit_code=0,
        )


__all__ = ["AIStatusController", "AIStatusOptions", "AIStatusResult"]
