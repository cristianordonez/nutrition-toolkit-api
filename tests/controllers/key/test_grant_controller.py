from __future__ import annotations

import typing
from types import SimpleNamespace

if typing.TYPE_CHECKING:
    from collections.abc import Callable


def test_grant_permissions_controller_run_returns_output(
    load_controller_module: Callable[[str], typing.Any],
    patch_key_controller_dependencies: Callable[
        ...,
        dict[str, list[tuple[object, str]]],
    ],
) -> None:
    grant_module = load_controller_module("ntk.controllers.key.grant")
    api_key = SimpleNamespace(name="demo-key")
    calls = patch_key_controller_dependencies(grant_module, api_keys=[api_key])
    options = grant_module.GrantOptions(api_key="plaintext-key", permissions=["read"])

    output = grant_module.GrantPermissionsController().run(options)

    assert output.controller == "grant-permissions"
    assert output.exit_code == 0
    assert output.result.permissions == ["read"]
    assert calls["granted"] == [(api_key, "read")]
