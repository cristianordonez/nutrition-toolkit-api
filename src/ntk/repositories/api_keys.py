from __future__ import annotations

from ntk.models.api_client import ApiClient


def get_api_clients() -> dict[str, ApiClient]:
    """Retrieve API client keys from PostgreSQL database.

    :return: A dictionary of API clients.
    """
    return {
        "production": ApiClient(
            name="production",
            api_key_hash="",
            permissions={"public"},
        ),
    }
