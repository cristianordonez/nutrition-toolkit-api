"""Thin HTTP client for cloud-api's Nutrition Care Process endpoints."""

from __future__ import annotations

import typing

import httpx

from ntk.models.ncp_public import NutritionCareProcessPublic

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest


class CloudAPIClient:
    """Call cloud-api's NCP-generation and retrieval endpoints over HTTP."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: float = 180.0,
    ) -> None:
        """Store the cloud-api base URL, credentials, and per-request timeout."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self, **extra: str) -> dict[str, str]:
        """Build request headers, including the bearer token cloud-api expects.

        Every Nutrition Care Process route is behind ``require_any_permission``,
        so a request without this header is rejected with 401 before it reaches
        the handler.
        """
        headers = dict(extra)
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        return headers

    async def generate_ncp(
        self,
        request: NCPGenerationRequest,
    ) -> NutritionCareProcessPublic:
        """POST a generation request and return the generated NCP."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/nutrition-care-processes/generate",
                content=request.model_dump_json(),
                headers=self._headers(**{"content-type": "application/json"}),
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
                headers=self._headers(),
            )
            response.raise_for_status()
            return [
                NutritionCareProcessPublic.model_validate(item)
                for item in response.json()
            ]


__all__ = ["CloudAPIClient"]
