"""UI-facing summary of locally persisted person data."""

from __future__ import annotations

from pydantic import BaseModel

from engine.models.base import ConsoleRenderableModel


class PersonSummaryField(BaseModel):
    """One high-value person field shown in the summary header."""

    key: str
    label: str
    value: str | None = None


class PersonDataCategory(BaseModel):
    """Available records in one clinical data category."""

    key: str
    label: str
    count: int
    detail: str | None = None


class MissingPersonData(BaseModel):
    """A clinically useful input that has not been documented."""

    key: str
    label: str
    reason: str


class PersonDataSummary(ConsoleRenderableModel):
    """Concise coverage summary for one selected person."""

    person_id: int
    name: str
    person_identifier: str | None = None
    overview: list[PersonSummaryField]
    categories: list[PersonDataCategory]
    missing: list[MissingPersonData]
    conflicts: list[str]

    def to_console(self) -> str:
        """Render the summary as formatted JSON."""
        return self.model_dump_json(indent=2)


__all__ = [
    "MissingPersonData",
    "PersonDataCategory",
    "PersonDataSummary",
    "PersonSummaryField",
]
