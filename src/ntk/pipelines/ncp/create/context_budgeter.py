"""Build and deterministically bound ncp-agent context."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.models.ncp_context import (
    BudgetedNCPContext,
    BudgetedPersonDetail,
)
from ntk.utils.tokens import count_tokens, truncate_to_tokens

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from ntk.models.person_detail import PersonDetail
    from ntk.models.rag import RagSearchMatch


_ADDITIONAL_CONTEXT_TOKENS = 1_000
_NCP_CHUNK_TOKENS = 1_200
_NCP_MATCH_LIMIT = 5


class ContextBudgetResult(BaseModel):
    """Typed agent context together with budgeting diagnostics."""

    ncp_context: BudgetedNCPContext
    omitted_record_counts: dict[str, int]
    raw_token_count: int
    final_token_count: int
    tokens_removed: int
    token_reduction_percent: float


class NCPContextBuilder:
    """Project complete person details onto the agent-facing person model."""

    @staticmethod
    def build(detail: PersonDetail) -> BudgetedPersonDetail:
        """Return all agent-relevant records before deterministic limits."""
        return BudgetedPersonDetail(
            name=detail.name,
            date_of_birth=detail.date_of_birth,
            age=detail.age,
            sex=detail.sex,
            height_in=detail.height_in,
            facility_name=detail.facility.name if detail.facility is not None else None,
            current_weight=detail.current_weight,
            current_diet=detail.current_diet,
            current_enteral_feeding=detail.current_enteral_feeding,
            current_parenteral_nutrition=detail.current_parenteral_nutrition,
            current_fluid_plan=detail.current_fluid_plan,
            current_dialysis=detail.current_dialysis,
            current_oral_feeding_status=detail.current_oral_feeding_status,
            current_weight_goal=detail.current_weight_goal,
            active_nutrition_goals=detail.active_nutrition_goals,
            active_diagnoses=detail.active_diagnoses,
            active_allergies=detail.active_allergies,
            relevant_medications=detail.active_medications,
            active_supplements=detail.active_supplements,
            active_food_preferences=detail.active_food_preferences,
            relevant_misc_orders=detail.active_misc_orders,
            weight_history=detail.weights,
            recent_labs=detail.labs,
            recent_edema=detail.edema,
            recent_meal_intakes=detail.meal_intakes,
            recent_appetite_observations=detail.appetite_observations,
            recent_gi_observations=detail.gi_observations,
            recent_wounds=detail.wounds,
            recent_clinical_facts=detail.clinical_facts,
            conflicts=detail.conflicts,
            derived_calculations=detail.derived_calculations,
        )


class ContextBudgeter:
    """Prioritize current nutrition state over lower-value historical records."""

    _LIST_LIMITS: typing.ClassVar[dict[str, int]] = {
        "active_nutrition_goals": 5,
        "active_diagnoses": 20,
        "active_allergies": 20,
        "relevant_medications": 15,
        "active_supplements": 10,
        "active_food_preferences": 15,
        "relevant_misc_orders": 5,
        "weight_history": 12,
        "recent_labs": 30,
        "recent_edema": 10,
        "recent_meal_intakes": 15,
        "recent_appetite_observations": 15,
        "recent_gi_observations": 15,
        "recent_wounds": 10,
        "recent_clinical_facts": 15,
        "conflicts": 20,
    }

    def __init__(
        self,
        context_builder: NCPContextBuilder | None = None,
    ) -> None:
        """Use the standard ncp projection unless one is supplied."""
        self.context_builder = context_builder or NCPContextBuilder()

    def budget(
        self,
        detail: PersonDetail,
        *,
        relevant_ncps: Sequence[RagSearchMatch] = (),
        additional_context: str | None = None,
    ) -> ContextBudgetResult:
        """Build the typed context and apply all deterministic size limits."""
        unbounded = BudgetedNCPContext(
            person=self.context_builder.build(detail),
            relevant_ncps=list(relevant_ncps),
            additional_context=self._normalize_context(additional_context),
        )
        raw_token_count = self._token_count(unbounded)
        person = unbounded.person.model_copy(deep=True)
        omitted: dict[str, int] = {}
        for name, limit in self._LIST_LIMITS.items():
            records = getattr(person, name)
            if len(records) <= limit:
                continue
            omitted[name] = len(records) - limit
            setattr(person, name, records[:limit])

        matches = list(unbounded.relevant_ncps)
        if len(matches) > _NCP_MATCH_LIMIT:
            omitted["relevant_ncps"] = len(matches) - _NCP_MATCH_LIMIT
        bounded = BudgetedNCPContext(
            person=person,
            relevant_ncps=[
                match.model_copy(
                    update={
                        "chunk_text": truncate_to_tokens(
                            match.chunk_text,
                            _NCP_CHUNK_TOKENS,
                        ),
                    },
                )
                for match in matches[:_NCP_MATCH_LIMIT]
            ],
            additional_context=(
                truncate_to_tokens(
                    unbounded.additional_context,
                    _ADDITIONAL_CONTEXT_TOKENS,
                )
                if unbounded.additional_context is not None
                else None
            ),
        )
        final_token_count = self._token_count(bounded)
        tokens_removed = max(0, raw_token_count - final_token_count)
        reduction_percent = (
            round(tokens_removed / raw_token_count * 100, 1) if raw_token_count else 0.0
        )
        return ContextBudgetResult(
            ncp_context=bounded,
            omitted_record_counts=omitted,
            raw_token_count=raw_token_count,
            final_token_count=final_token_count,
            tokens_removed=tokens_removed,
            token_reduction_percent=reduction_percent,
        )

    @staticmethod
    def _normalize_context(context: str | None) -> str | None:
        if context is None:
            return None
        normalized = context.strip()
        return normalized or None

    @staticmethod
    def _token_count(context: BudgetedNCPContext) -> int:
        return count_tokens(context.model_dump_json(exclude_none=True))


__all__ = ["ContextBudgetResult", "ContextBudgeter"]
