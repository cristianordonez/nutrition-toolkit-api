from __future__ import annotations

import typing

from ntk.models.api_key import APIKey

if typing.TYPE_CHECKING:
    from collections.abc import Callable


def test_list_controller_run_returns_output(
    load_controller_module: Callable[[str], typing.Any],
    patch_key_controller_dependencies: Callable[
        ...,
        dict[str, list[tuple[object, str]]],
    ],
) -> None:
    list_module = load_controller_module("ntk.controllers.key.list")
    api_key = APIKey(name="demo-key", api_key_hash="hash", permissions=[])
    patch_key_controller_dependencies(list_module, api_keys=[api_key])
    options = list_module.ListOptions(api_key="plaintext-key")

    output = list_module.ListController().run(options)

    assert output.controller == "list"
    assert output.exit_code == 0
    assert output.result.api_keys == [api_key]
