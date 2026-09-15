from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

_TEST_FOO = 5


class DummyOptions(BaseModel):
    foo: int = Field(description="Foo value", default=1)
    bar: str = Field(description="Bar value")
    flag: bool = Field(description="Flag value", default=False)
    mode: typing.Literal["a", "b"] = Field(description="Mode", default="a")
    optional_tuple: tuple[int, int] | None = Field(
        description="Optional tuple",
        default=None,
    )


class DummyResponse(ConsoleRenderableModel):
    foo: int
    bar: str
    flag: bool
    mode: str
    optional_tuple: tuple[int, int] | None = None

    def to_console(self) -> str:
        return f"Foo: {self.foo}, Bar: {self.bar}, Flag: {self.flag}, Mode: {self.mode}"


class DummyController(BaseController[DummyOptions]):  # ty: ignore
    name = "dummy"
    help = "Dummy command"
    options_model = DummyOptions

    def run(self, options: DummyOptions) -> Output:
        result = DummyResponse(
            foo=options.foo,
            bar=options.bar,
            flag=options.flag,
            mode=options.mode,
            optional_tuple=options.optional_tuple,
        )
        return Output(controller=self.name, result=result, exit_code=0)


def test_run_with_options_returns_output() -> None:
    controller = DummyController()
    options = DummyOptions(bar="test")
    output = controller.run(options)

    assert output.controller == "dummy"
    assert output.result == DummyResponse(
        foo=1,
        bar="test",
        flag=False,
        mode="a",
        optional_tuple=None,
    )
    assert output.exit_code == 0
