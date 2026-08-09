from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable


def _assert_equal(actual: object, expected: object, description: str) -> None:
    if actual != expected:
        msg = f"{description}: expected {expected!r}, got {actual!r}"
        raise AssertionError(msg)


def test_create_controller_run_returns_output(
    load_controller_module: Callable[[str], typing.Any],
    patch_key_controller_dependencies: Callable[
        ...,
        dict[str, list[tuple[object, str]]],
    ],
) -> None:
    create_module = load_controller_module("ntk.controllers.key.create")
    calls = patch_key_controller_dependencies(create_module)
    options = create_module.CreateKeyOptions(name="demo-key", permissions=["read"])

    output = create_module.CreateController().run(options)

    _assert_equal(output.controller, "create", "controller")
    _assert_equal(output.exit_code, 0, "exit code")
    _assert_equal(output.result.plaintext_key, "generated-key", "plaintext key")
    _assert_equal(output.result.api_key_name, "demo-key", "API key name")
    _assert_equal(output.result.api_key_permissions, ["read"], "API key permissions")
    _assert_equal(calls["created"], [("demo-key", "read")], "creation calls")
