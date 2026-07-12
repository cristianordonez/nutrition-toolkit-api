from __future__ import annotations

from pydantic import BaseModel


class ApiClient(BaseModel):
    """API Client Model."""

    name: str
    api_key_hash: str
    permissions: set[str]
    active: bool = True
