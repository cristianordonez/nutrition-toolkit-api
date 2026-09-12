from __future__ import annotations

import requests
from starlette.status import HTTP_401_UNAUTHORIZED

from ntk.models.settings import SETTINGS

TOKEN_URL = "https://oauth.fatsecret.com/connect/token"  # noqa: S105
BASE_URL = "https://platform.fatsecret.com/rest/"
SEARCH_URL = f"{BASE_URL}foods/search/v1"
BRANDS_URL = f"{BASE_URL}brands/v2"


class FatSecretService:
    def __init__(self) -> None:
        """Init client."""
        self.client_id = SETTINGS.fatsecret_client_id
        self.client_secret = SETTINGS.fatsecret_client_secret
        self.access_token: str | None = None
        self._authenticate()

    def _authenticate(self) -> None:
        response = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": "basic",
            },
            timeout=30,
        )
        response.raise_for_status()
        self.access_token = response.json()["access_token"]

    def search_foods(self, search: str) -> dict:
        """Search foods from fatsecret API.

        :param search: search query
        :return: API results
        """
        if self.access_token is None:
            self._authenticate()
        response = requests.get(
            SEARCH_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
            },
            params={
                "search_expression": search,
                "format": "json",
                "max_results": 20,
            },
            timeout=30,
        )
        if response.status_code == HTTP_401_UNAUTHORIZED:
            self._authenticate()
            response = requests.get(
                SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                },
                params={
                    "search_expression": search,
                    "format": "json",
                    "max_results": 20,
                },
                timeout=30,
            )
        response.raise_for_status()
        return response.json()


# Preserve the existing public name while callers migrate to the service naming.
FatSecretClient = FatSecretService

__all__ = ["FatSecretClient", "FatSecretService"]
