from __future__ import annotations

import asyncio
import json
import pathlib
import typing
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic_ai.models.test import TestModel

from ntk.agents import assessment_agent
from ntk.agents.assessment_agent import (
    AssessmentAgent,
    AssessmentGenerationTimeoutError,
)
from ntk.agents.tools import AssessmentToolDependencies
from ntk.models.assessment_context import (
    BudgetedAssessmentContext,
    BudgetedPersonDetail,
)
from ntk.models.person_detail import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    TubeFeedCalculation,
)
from ntk.models.rag import RagSearchMatch

if typing.TYPE_CHECKING:
    from pydantic_ai.models import ModelRequestParameters

PERSON_AGE = 80
_FOOD_REPO = object()
_EMBEDDING_SERVICE = object()


class FakeAgent:
    def __init__(self, output: str) -> None:
        self.output = output
        self.prompt = ""
        self.deps: object | None = None

    async def run(self, prompt: str, **kwargs: object) -> object:
        self.prompt = prompt
        self.deps = kwargs.get("deps")
        return SimpleNamespace(output=self.output)


def _calculations() -> DerivedPersonCalculations:
    return DerivedPersonCalculations(
        calculated_on=date(2026, 9, 7),
        anthropometrics=AnthropometricCalculations(),
        nutrition_needs=NutritionNeedsCalculation(status="not_computed"),
        tube_feed=TubeFeedCalculation(status="not_applicable"),
        parenteral_nutrition=ParenteralNutritionCalculation(
            status="not_applicable",
        ),
    )


def _context() -> BudgetedAssessmentContext:
    return BudgetedAssessmentContext(
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            age=PERSON_AGE,
            derived_calculations=_calculations(),
        ),
        relevant_assessments=[
            RagSearchMatch(
                document_id=1,
                filename="assessment.txt",
                chunk_text="Style example",
                similarity=0.9,
            ),
        ],
        additional_context="wound healing",
    )


def test_assessment_agent_passes_prepared_context_and_tool_dependencies() -> None:
    fake = FakeAgent("  Nutrition Readmission Assessment  ")

    result = asyncio.run(
        AssessmentAgent(
            agent=fake,  # ty: ignore[invalid-argument-type]
            food_repo=_FOOD_REPO,  # ty: ignore[invalid-argument-type]
            embedding_service=_EMBEDDING_SERVICE,  # ty: ignore[invalid-argument-type]
        ).run(_context()),
    )

    payload = json.loads(fake.prompt)
    assert payload["person"]["age"] == PERSON_AGE
    assert payload["relevant_assessments"][0]["chunk_text"] == "Style example"
    assert payload["additional_context"] == "wound healing"
    assert isinstance(fake.deps, AssessmentToolDependencies)
    assert fake.deps.food_repo is _FOOD_REPO
    assert fake.deps.embedding_service is _EMBEDDING_SERVICE
    assert result == "Nutrition Readmission Assessment"


def test_assessment_agent_registers_calculator_and_knowledge_tools() -> None:
    model = TestModel(call_tools=[], custom_output_text="done")
    dependencies = AssessmentToolDependencies(
        food_repo=typing.cast("typing.Any", _FOOD_REPO),
        embedding_service=typing.cast("typing.Any", _EMBEDDING_SERVICE),
    )

    with assessment_agent.assessment_agent.override(model=model):
        asyncio.run(
            assessment_agent.assessment_agent.run(
                "Inspect assessment tools",
                deps=dependencies,
            ),
        )

    request_parameters = typing.cast(
        "ModelRequestParameters",
        model.last_model_request_parameters,
    )
    assert {tool.name for tool in request_parameters.function_tools} == {
        "calculate_nutrition_needs",
        "calculate_tube_feed",
        "get_knowledge_from_diet_manual",
        "get_knowledge_from_nutrition_care_manual",
    }


def test_assessment_agent_rejects_empty_note() -> None:
    with pytest.raises(RuntimeError, match="empty note"):
        asyncio.run(
            AssessmentAgent(
                agent=FakeAgent("  "),  # ty: ignore[invalid-argument-type]
                food_repo=_FOOD_REPO,  # ty: ignore[invalid-argument-type]
                embedding_service=_EMBEDDING_SERVICE,  # ty: ignore[invalid-argument-type]
            ).run(_context()),
        )


def test_assessment_agent_times_out_stalled_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StalledAgent:
        @staticmethod
        async def run(_prompt: str, **_kwargs: object) -> object:
            await asyncio.sleep(1)
            return SimpleNamespace(output="late")

    monkeypatch.setattr(
        assessment_agent,
        "_ASSESSMENT_GENERATION_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(AssessmentGenerationTimeoutError, match="timed out"):
        asyncio.run(
            AssessmentAgent(
                agent=StalledAgent(),  # ty: ignore[invalid-argument-type]
                food_repo=_FOOD_REPO,  # ty: ignore[invalid-argument-type]
                embedding_service=_EMBEDDING_SERVICE,  # ty: ignore[invalid-argument-type]
            ).run(_context()),
        )


def test_assessment_agent_requires_tool_dependencies() -> None:
    with pytest.raises(RuntimeError, match="food repository"):
        asyncio.run(
            AssessmentAgent(
                agent=FakeAgent("unused"),  # ty: ignore[invalid-argument-type]
            ).run(_context()),
        )

    with pytest.raises(RuntimeError, match="embedding service"):
        asyncio.run(
            AssessmentAgent(
                agent=FakeAgent("unused"),  # ty: ignore[invalid-argument-type]
                food_repo=_FOOD_REPO,  # ty: ignore[invalid-argument-type]
            ).run(_context()),
        )


def test_assessment_prompt_defines_budgeted_context_contract() -> None:
    prompt = (
        pathlib.Path(__file__).parents[2]
        / "src/ntk/agents/prompts/assessment_prompt.md"
    ).read_text(encoding="utf-8")

    assert "## Inputs and evidence" in prompt
    assert "`person`" in prompt
    assert "`relevant_assessments`" in prompt
    assert "`additional_context`" in prompt
    assert "Treat `person.derived_calculations` as the authoritative source" in prompt
    assert "Call `calculate_nutrition_needs` only when" in prompt
    assert "Call `calculate_tube_feed` only when" in prompt
    assert "Call `get_knowledge_from_nutrition_care_manual` when" in prompt
    assert "Call `get_knowledge_from_diet_manual` when" in prompt
    assert "Do not search either manual for resident-specific facts" in prompt
    assert "always call the subject the `resident` or `res`" in prompt
    assert '"Resident is a [age] yo [gender]' in prompt
    assert "never as `person`, `patient`, `client`, or `individual`" in prompt
    assert "If formula lookup is ambiguous" in prompt
    assert "Do not perform BMI, weight-change, nutrition-needs" in prompt
    assert "state the latest weight once in the `Weight/BMI:` line" in prompt
    assert "copy each `comparison_text`" in prompt
    assert "verbatim on its own new line" in prompt
    assert "Every statement describing weight loss or weight gain" in prompt
    assert "calendar-based elapsed time rounded to whole months" in prompt
    assert "Significant weight-change rationale:" in prompt
    assert (
        "Weight change rationale: Cause undetermined from available records." in prompt
    )
    assert (
        "Apply this requirement to both significant loss and significant gain" in prompt
    )
    assert "compare prior weights with one another" in prompt
    assert "interpret the entire supplied weight trend" in prompt
    assert "continued change or recent stabilization" in prompt
    assert "resident's full supplied clinical picture" in prompt
    assert "A new intervention is then not automatically required" in prompt
    assert "current plan is adequate" in prompt
    assert "dated `recent_clinical_facts` entry" in prompt
    assert "their presence does not prove adequate intake" in prompt
    assert "missing or stale evidence of current meal/supplement acceptance" in prompt
    assert "does not satisfy the response to significant weight loss" in prompt
    assert "Do not infer adequacy from active orders alone" in prompt
    assert (
        "the measurement date is required whenever the latest weight is present"
        in prompt
    )
    assert "Never convert the supplied month timeframe back to days" in prompt
    assert "Never print fractional months" in prompt
    assert "## Style" in prompt
    assert "## Final validation" in prompt
    assert "resolved, healed, or closed" in prompt
    assert "always state `Malnutrition status:`" in prompt
    assert "six diagnostic characteristics" in prompt
    assert "BMI is not an Academy/ASPEN diagnostic characteristic" in prompt
    assert "at least two of the six characteristics meet severe thresholds" in prompt
    assert "Meal-completion percentages and appetite descriptions alone" in prompt
    assert "Albumin, prealbumin, total protein" in prompt
    assert "`Risk for malnutrition` is a screening/clinical-risk conclusion" in prompt
