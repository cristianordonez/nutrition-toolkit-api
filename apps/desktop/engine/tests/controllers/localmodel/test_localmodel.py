from __future__ import annotations

import asyncio

import pytest

from engine.clients.ollama_client import OllamaUnavailableError
from engine.controllers.localmodel.ensure import (
    LocalModelEnsureController,
    LocalModelEnsureOptions,
)
from engine.controllers.localmodel.status import (
    LocalModelStatusController,
    LocalModelStatusOptions,
)
from engine.services import local_model


class _Client:
    """Stands in for a local Ollama daemon."""

    def __init__(
        self,
        *,
        running: bool = True,
        models: list[str] | None = None,
    ) -> None:
        self.running = running
        self.models = models or []
        self.pulled: list[str] = []

    async def is_available(self) -> bool:
        return self.running

    async def has_model(self, model: str) -> bool:
        return model in self.models

    async def pull(self, model: str, on_progress: object = None) -> None:
        del on_progress
        if not self.running:
            msg = "daemon down"
            raise OllamaUnavailableError(msg)
        self.pulled.append(model)
        self.models.append(model)


def _status(client: _Client) -> object:
    controller = LocalModelStatusController(client=client)  # ty: ignore[invalid-argument-type]
    return asyncio.run(controller.run(LocalModelStatusOptions())).result


def test_status_reports_a_ready_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_model, "total_ram_gb", lambda: 24)
    result = _status(_Client(models=["qwen2.5:14b"]))

    assert result.supported is True
    assert result.model == "qwen2.5:14b"
    assert result.ollama_running is True
    assert result.model_downloaded is True


def test_status_reports_a_missing_daemon() -> None:
    result = _status(_Client(running=False))

    assert result.ollama_running is False
    # Nothing can be downloaded if the daemon never answered.
    assert result.model_downloaded is False


def test_status_explains_an_unsupported_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_model, "total_ram_gb", lambda: 8)
    result = _status(_Client())

    assert result.supported is False
    assert result.model is None
    assert result.detail is not None
    assert "at least 16 GB" in result.detail


def test_ensure_pulls_only_when_the_model_is_missing() -> None:
    client = _Client(models=[])
    controller = LocalModelEnsureController(client=client)  # ty: ignore[invalid-argument-type]

    first = asyncio.run(controller.run(LocalModelEnsureOptions())).result
    assert first.downloaded is True
    assert first.already_present is False
    assert client.pulled == [first.model]

    second = asyncio.run(controller.run(LocalModelEnsureOptions())).result
    assert second.downloaded is False
    assert second.already_present is True
    # Still only the one pull; the second call short-circuited.
    assert client.pulled == [first.model]


def test_ensure_refuses_an_unsupported_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_model, "total_ram_gb", lambda: 4)
    client = _Client()
    controller = LocalModelEnsureController(client=client)  # ty: ignore[invalid-argument-type]

    with pytest.raises(OllamaUnavailableError, match="at least 16 GB"):
        asyncio.run(controller.run(LocalModelEnsureOptions()))

    assert client.pulled == []
