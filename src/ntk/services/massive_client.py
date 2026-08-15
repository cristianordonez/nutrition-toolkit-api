"""Client for the Massive API.

The API key is stored in a Databricks secret scope (see setup_secrets.py) and
resolved at runtime via the Databricks SDK - it is never stored in code, env
files, or app.yaml.
"""

from __future__ import annotations

import base64
import os
import typing

import requests
from databricks.sdk import WorkspaceClient

if typing.TYPE_CHECKING:
    from collections.abc import Generator

_w = WorkspaceClient()

_SCOPE = os.environ.get("MASSIVE_SECRET_SCOPE", "massive")
_KEY = os.environ.get("MASSIVE_SECRET_KEY", "api-key")
_BASE_URL = os.environ.get("MASSIVE_API_BASE_URL", "https://api.massive.com")

_DEFAULT_TIMEOUT = 30


def _get_api_key() -> str:
    """Fetch and decode the Massive API key from the Databricks secret scope."""
    secret = _w.secrets.get_secret(scope=_SCOPE, key=_KEY)
    return base64.b64decode(secret.value).decode("utf-8")


class MassiveClient:
    """Thin wrapper around the Massive API with auth + retry-friendly session."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        """Init client.

        :param base_url: API URL, defaults to None
        :param timeout: seconds until timeout, defaults to _DEFAULT_TIMEOUT
        """
        self.base_url = (base_url or _BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {_get_api_key()}",
                "Content-Type": "application/json",
            },
        )

    def get(self, path: str, params: dict[str, typing.Any] | None = None) -> str:
        """Get stocks.

        :param path: path to url
        :param params: api paramsi, defaults to None
        :return: string
        """
        resp = self._session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json: dict[str, typing.Any] | None = None) -> str:
        """Post to client.

        :param path: path to url
        :param json: json string, defaults to None
        :return: json
        """
        resp = self._session.post(
            f"{self.base_url}{path}",
            json=json,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def paginated_get(
        self,
        path: str,
        params: dict[str, typing.Any] | None = None,
        page_size: int = 200,
    ) -> Generator:
        """Yield items across all pages of a "massive" (large).

        Paginated dataset. Assumes a cursor-based API shape:
        {"items": [...], "next_cursor": "..." | null}
        Adjust to match the real Massive API pagination contract.
        """
        cursor = None
        params = dict(params or {})
        params["page_size"] = page_size

        while True:
            if cursor:
                params["cursor"] = cursor
            data = self.get(path, params=params)
            items = data.get("items", [])
            yield from items

            cursor = data.get("next_cursor")
            if not cursor:
                break

    def get_latest_price(self, symbol: str) -> dict:
        """Fetch the latest traded price for a single symbol in a SINGLE API.

        No pagination. Use this instead of paginated_get() whenever
        the caller needs to stay within tight API rate limits (e.g.
        classroom/student accounts), at the cost of only being able to
        request one symbol per request.
        """
        return self.get(f"/v2/aggs/ticker/{symbol}/prev")
