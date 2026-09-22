"""Thin HTTP client for cloud-api's Nutrition Care Process endpoints."""

from __future__ import annotations

import typing

import httpx

from ntk.models.ncp_public import NutritionCareProcessPublic

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest


class CloudAPIUnavailableError(RuntimeError):
    """Raised when cloud-api cannot be reached at all.

    Distinguished from an error cloud-api itself returned: nothing was served,
    so the caller's request was never seen. httpx's own ``ConnectError`` says
    only "All connection attempts failed", which does not name what was being
    connected to.
    """


#: cloud-api mounts every router under this prefix (see its ``main.py``). The
#: configured base URL is the host, so the version the client speaks belongs
#: here rather than in each deployment's settings.
_API_PREFIX = "/api/v1"


class CloudAPIClient:
    """Call cloud-api's NCP-generation and retrieval endpoints over HTTP."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: float = 180.0,
    ) -> None:
        """Store the cloud-api base URL, credentials, and per-request timeout.

        ``base_url`` is the host, with or without the version prefix -- a
        configured value that already ends in it is accepted rather than
        doubled.
        """
        root = base_url.rstrip("/").removesuffix(_API_PREFIX)
        self._base_url = f"{root}{_API_PREFIX}"
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
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/nutrition-care-processes/generate",
                    content=request.model_dump_json(),
                    headers=self._headers(**{"content-type": "application/json"}),
                )
                response.raise_for_status()
                return NutritionCareProcessPublic.model_validate(response.json())
        except httpx.ConnectError as error:
            raise self._unavailable() from error

    async def list_ncps(
        self,
        person_identifier: str,
    ) -> list[NutritionCareProcessPublic]:
        """Return every Nutrition Care Process for one person identifier."""
        try:
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
        except httpx.ConnectError as error:
            raise self._unavailable() from error

    def _unavailable(self) -> CloudAPIUnavailableError:
        """Name the host that could not be reached, and why it is needed."""
        message = (
            f"Could not reach cloud-api at {self._base_url}. Note generation "
            "and note history live there and have no on-device fallback, so "
            "start cloud-api and try again."
        )
        return CloudAPIUnavailableError(message)


__all__ = ["CloudAPIClient", "CloudAPIUnavailableError"]
