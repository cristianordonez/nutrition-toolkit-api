"""The complete context assembled cloud-side before invoking the NCP agent."""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC001, TC003

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ntk.models.ncp_context import BudgetedPersonDetail

from .rag import RagSearchMatch


class PreviousNCPNote(BaseModel):
    """A resident's own most recent finalized Nutrition Care Process note."""

    model_config = ConfigDict(extra="forbid")

    note_date: date
    note_text: str


class BudgetedNCPContext(BaseModel):
    """Complete data payload prepared before invoking the NCP agent."""

    model_config = ConfigDict(extra="forbid")

    person: BudgetedPersonDetail
    previous_ncp: PreviousNCPNote | None = None
    relevant_ncps: list[RagSearchMatch] = Field(default_factory=list)
    additional_context: str | None = None


__all__ = ["BudgetedNCPContext", "PreviousNCPNote"]
