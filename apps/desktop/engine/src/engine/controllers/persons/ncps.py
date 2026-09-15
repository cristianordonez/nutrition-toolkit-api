"""Return Nutrition Care Processes for a person, fetched from cloud-api."""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.clients.cloud_api_client import CloudAPIClient
from engine.models.settings import SETTINGS
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.ncp_public import NutritionCareProcessPublic  # noqa: TC001
from ntk.models.output import Output


class PersonNCPsOptions(BaseModel):
    """Person identifier whose Nutrition Care Processes should be returned."""

    person_identifier: str = Field(
        min_length=1,
        description="The person's external identifier",
    )


class PersonNCPsResult(ConsoleRenderableModel):
    """Nutrition Care Processes belonging to the requested person."""

    ncps: list[NutritionCareProcessPublic]

    def to_console(self) -> str:
        """Render ncps as formatted JSON."""
        return self.model_dump_json(indent=2)


class PersonNCPsController(BaseController):
    """Retrieve Nutrition Care Processes for one person from cloud-api."""

    name = "ncps"
    help = "Get Nutrition Care Processes by person identifier"
    options_model = PersonNCPsOptions

    def __init__(self, client: CloudAPIClient | None = None) -> None:
        """Store the cloud-api client used to fetch NCPs."""
        self.client = client or CloudAPIClient(str(SETTINGS.cloud_api_base_url))

    async def run(
        self,
        options: PersonNCPsOptions,
    ) -> Output[PersonNCPsResult]:
        """Return NCPs for the supplied person identifier."""
        ncps = await self.client.list_ncps(options.person_identifier)
        return Output(
            result=PersonNCPsResult(ncps=ncps),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "PersonNCPsController",
    "PersonNCPsOptions",
    "PersonNCPsResult",
]
