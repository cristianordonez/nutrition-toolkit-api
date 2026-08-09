from __future__ import annotations

import typing

from ntk.models.api_key import APIKey

if typing.TYPE_CHECKING:
    from collections.abc import Callable


def test_revoke_controller_run_returns_output(
    load_controller_module: Callable[[str], typing.Any],
    patch_key_controller_dependencies: Callable[
        ...,
        dict[str, list[tuple[object, str]]],
    ],
) -> None:
    revoke_module = load_controller_module("ntk.controllers.key.revoke")
    revoked_key = APIKey(name="demo-key", api_key_hash="hash", permissions=[])
    patch_key_controller_dependencies(revoke_module, revoked_key=revoked_key)
    options = revoke_module.RevokeOptions(api_key="plaintext-key")

    output = revoke_module.RevokeController().run(options)

    assert output.controller == "revoke"
    assert output.exit_code == 0
    assert output.result.revoked_key is revoked_key
