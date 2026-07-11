from __future__ import annotations

import typing

from pydantic import Field

from ntk.controllers.base import BaseController
from ntk.models.base import CustomBaseSettings
from ntk.models.output import Output

# ruff: noqa: S101


_TEST_FOO = 5


class DummyOptions(CustomBaseSettings):
    foo: int = Field(description="Foo value", default=1)
    bar: str = Field(description="Bar value")
    flag: bool = Field(description="Flag value", default=False)
    mode: typing.Literal["a", "b"] = Field(description="Mode", default="a")
    optional_tuple: tuple[int, int] | None = Field(
        description="Optional tuple",
        default=None,
    )


class DummyController(BaseController[DummyOptions]):
    name = "dummy"
    help = "Dummy command"
    options_model = DummyOptions

    def run(self, options: DummyOptions) -> Output:
        return Output(controller=self.name, result={"bar": options.bar}, exit_code=0)


def test_run_with_options_returns_output() -> None:
    controller = DummyController()
    options = DummyOptions(bar="test")
    output = controller.run(options)

    assert output.controller == "dummy"
    assert output.result == {"bar": "test"}
    assert output.exit_code == 0
