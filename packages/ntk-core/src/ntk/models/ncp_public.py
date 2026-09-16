"""Public wire representation of a Nutrition Care Process record.

Shared by cloud-api (which serializes ``NutritionCareProcess`` rows into this
shape) and engine's HTTP client (which parses responses into it), so the two
apps agree on the NCP response contract without engine importing cloud's
SQLModel classes.
"""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC003

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NutritionCareProcessPublic(BaseModel):
    """One Nutrition Care Process record as returned over HTTP."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    person_identifier: str
    facility_identifier: str | None = None
    note_text: str
    content_hash: str
    created_by: str
    status: str
    model_name: str | None = None
    created_at: datetime
    finalized_at: datetime | None = None


__all__ = ["NutritionCareProcessPublic"]
