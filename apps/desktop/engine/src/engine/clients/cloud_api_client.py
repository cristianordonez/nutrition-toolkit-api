"""Thin HTTP client for cloud-api's Nutrition Care Process endpoints."""

from __future__ import annotations

import typing

import httpx

from ntk.models.ncp_public import NutritionCareProcessPublic

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest


class CloudAPIClient:
    """Call cloud-api's NCP-generation and retrieval endpoints over HTTP."""

    def __init__(self, base_url: str, *, timeout: float = 180.0) -> None:
        """Store the cloud-api base URL and per-request timeout."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def generate_ncp(
        self,
        request: NCPGenerationRequest,
    ) -> NutritionCareProcessPublic:
        """POST a generation request and return the generated NCP."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/nutrition-care-processes/generate",
                content=request.model_dump_json(),
                headers={"content-type": "application/json"},
            )
            response.raise_for_status()
            return NutritionCareProcessPublic.model_validate(response.json())

    async def list_ncps(
        self,
        person_identifier: str,
    ) -> list[NutritionCareProcessPublic]:
        """Return every Nutrition Care Process for one person identifier."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/nutrition-care-processes",
                params={"person_identifier": person_identifier},
            )
            response.raise_for_status()
            return [
                NutritionCareProcessPublic.model_validate(item)
                for item in response.json()
            ]


__all__ = ["CloudAPIClient"]
