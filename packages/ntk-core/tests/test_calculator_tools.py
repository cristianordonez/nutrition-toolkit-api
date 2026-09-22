"""Tests for agent calculator-tool registration."""

from __future__ import annotations

import typing

from pydantic_ai import Agent, FunctionToolset
from pydantic_ai.models.test import TestModel

from ntk.agents.calculator_tools import (
    CALCULATOR_TOOLSET,
    CalculatorToolDependencies,
)

if typing.TYPE_CHECKING:
    from pydantic_ai.models import ModelRequestParameters


_DEPENDENCIES = CalculatorToolDependencies()


def test_calculators_are_registered_as_a_function_toolset() -> None:
    assert isinstance(CALCULATOR_TOOLSET, FunctionToolset)


def test_only_the_nutrition_needs_calculator_is_an_agent_tool() -> None:
    """Tube-feed calculation moved fully on-device; only one tool remains here."""
    model = TestModel(call_tools=[], custom_output_text="done")
    agent = Agent(
        model,
        output_type=str,
        deps_type=CalculatorToolDependencies,
        toolsets=[CALCULATOR_TOOLSET],
    )

    agent.run_sync("List the available calculator tools", deps=_DEPENDENCIES)

    request_parameters = typing.cast(
        "ModelRequestParameters",
        model.last_model_request_parameters,
    )
    tool_names = {tool.name for tool in request_parameters.function_tools}
    assert tool_names == {"calculate_nutrition_needs"}


def test_calculator_toolset_array_schemas_define_items() -> None:
    model = TestModel(call_tools=[], custom_output_text="done")
    Agent(
        model,
        output_type=str,
        deps_type=CalculatorToolDependencies,
        toolsets=[CALCULATOR_TOOLSET],
    ).run_sync(
        "Inspect calculator schemas",
        deps=_DEPENDENCIES,
    )
    request_parameters = typing.cast(
        "ModelRequestParameters",
        model.last_model_request_parameters,
    )

    for tool in request_parameters.function_tools:
        _assert_array_items(tool.parameters_json_schema)


def test_nutrition_calculator_tool_parameters_have_descriptions() -> None:
    model = TestModel(call_tools=[], custom_output_text="done")
    Agent(
        model,
        output_type=str,
        deps_type=CalculatorToolDependencies,
        toolsets=[CALCULATOR_TOOLSET],
    ).run_sync(
        "Inspect calculator schemas",
        deps=_DEPENDENCIES,
    )
    request_parameters = typing.cast(
        "ModelRequestParameters",
        model.last_model_request_parameters,
    )

    nutrition_tool_names = {"calculate_nutrition_needs"}
    nutrition_tools = [
        tool
        for tool in request_parameters.function_tools
        if tool.name in nutrition_tool_names
    ]

    assert {tool.name for tool in nutrition_tools} == nutrition_tool_names
    for tool in nutrition_tools:
        properties = tool.parameters_json_schema["properties"]
        assert all("description" in value for value in properties.values()), tool.name


def _assert_array_items(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "array":
            assert "items" in schema, schema
        for value in schema.values():
            _assert_array_items(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_array_items(value)
