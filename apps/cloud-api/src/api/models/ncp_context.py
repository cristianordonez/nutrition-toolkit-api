"""The complete context assembled cloud-side before invoking the NCP agent."""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC001

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ntk.models.ncp_context import BudgetedPersonDetail

from .rag import RagSearchMatch


class BudgetedNCPContext(BaseModel):
    """Complete data payload prepared before invoking the NCP agent."""

    model_config = ConfigDict(extra="forbid")

    person: BudgetedPersonDetail
    relevant_ncps: list[RagSearchMatch] = Field(default_factory=list)
    additional_context: str | None = None


__all__ = ["BudgetedNCPContext"]
