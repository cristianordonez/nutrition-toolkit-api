from __future__ import annotations

import typing
from types import SimpleNamespace

if typing.TYPE_CHECKING:
    from collections.abc import Callable


def test_revoke_permissions_controller_run_returns_output(
    load_controller_module: Callable[[str], typing.Any],
    patch_key_controller_dependencies: Callable[
        ...,
        dict[str, list[tuple[object, str]]],
    ],
) -> None:
    revoke_permission_module = load_controller_module(
        "ntk.controllers.key.revoke_permission",
    )
    api_key = SimpleNamespace(name="demo-key")
    calls = patch_key_controller_dependencies(
        revoke_permission_module,
        api_keys=[api_key],
    )
    options = revoke_permission_module.RevokePermissionsOptions(
        api_key="plaintext-key",
        permissions=["read"],
    )

    output = revoke_permission_module.RevokePermissionsController().run(options)

    assert output.controller == "revoke-permissions"
    assert output.exit_code == 0
    assert output.result.permissions == ["read"]
    assert calls["revoked"] == [(api_key, "read")]
