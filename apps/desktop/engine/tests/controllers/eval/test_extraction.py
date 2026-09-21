from __future__ import annotations

import asyncio
import pathlib
import typing

import pytest

from engine.controllers.eval import extraction as eval_module
from engine.controllers.eval.extraction import (
    EvalExtractionController,
    EvalExtractionOptions,
)


class _Payload:
    def __init__(self, type_: str) -> None:
        self.type = type_


class _Fact:
    def __init__(self, type_: str) -> None:
        self.payload = _Payload(type_)


class _FakeAgent:
    """Carries only the model name the report reads."""

    model = type("M", (), {"model_name": "test-model"})()


class _Extractor:
    """Stands in for the real unknown-document extractor."""

    calls: typing.ClassVar[list[pathlib.Path]] = []
    facts: typing.ClassVar[list[str]] = ["wound", "wound", "appetite"]
    explode: typing.ClassVar[bool] = False

    def __init__(self, file: pathlib.Path, **_kwargs: object) -> None:
        if self.explode:
            msg = "unsupported file"
            raise ValueError(msg)
        self.file = file
        self.calls.append(file)

    async def extract(self) -> list[_Fact]:
        return [_Fact(name) for name in self.facts]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test off the network and away from real settings."""
    _Extractor.calls = []
    _Extractor.explode = False
    monkeypatch.setattr(eval_module, "UnknownFileExtractor", _Extractor)
    monkeypatch.setattr(
        eval_module,
        "build_unknown_document_agent",
        lambda _provider=None: _FakeAgent(),
    )


def _run(providers: list[str], files: list[str] | None = None) -> object:
    controller = EvalExtractionController()
    options = EvalExtractionOptions(
        files=[pathlib.Path(name) for name in (files or ["note.pdf"])],
        providers=providers,
    )
    return asyncio.run(controller.run(options)).result


def test_counts_facts_and_times_each_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        EvalExtractionController,
        "_preflight",
        staticmethod(lambda _provider: asyncio.sleep(0, result=None)),
    )

    result = _run(["openai"], ["a.pdf", "b.pdf"])

    run = result.runs[0]
    assert run.total_facts == 6  # 3 facts x 2 documents  # noqa: PLR2004
    assert run.fact_types == {"appetite": 2, "wound": 4}
    assert [doc.document for doc in run.documents] == ["a.pdf", "b.pdf"]
    assert all(doc.seconds >= 0 for doc in run.documents)


def test_a_blocked_provider_explains_itself_instead_of_reporting_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        EvalExtractionController,
        "_preflight",
        staticmethod(
            lambda _provider: asyncio.sleep(0, result="Ollama is not running."),
        ),
    )

    run = _run(["ollama"]).runs[0]

    # The distinction that matters: nothing ran, so this must not look like a
    # model that found no facts.
    assert run.error == "Ollama is not running."
    assert run.total_facts == 0
    assert run.documents == []
    assert _Extractor.calls == []


def test_one_unreadable_document_does_not_end_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        EvalExtractionController,
        "_preflight",
        staticmethod(lambda _provider: asyncio.sleep(0, result=None)),
    )
    _Extractor.explode = True

    run = _run(["openai"]).runs[0]

    assert run.total_facts == 0
    assert run.documents[0].error is not None
    assert "unsupported file" in run.documents[0].error


def test_console_output_compares_providers_side_by_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        EvalExtractionController,
        "_preflight",
        staticmethod(lambda _provider: asyncio.sleep(0, result=None)),
    )

    rendered = _run(["openai", "ollama"]).to_console()

    assert "provider" in rendered
    assert rendered.count("test-model") >= 2  # noqa: PLR2004
    assert "openai" in rendered
    assert "ollama" in rendered


def test_counting_agent_records_failures_before_they_are_swallowed() -> None:
    class _Failing:
        model = _FakeAgent.model

        async def run(self, *_args: object, **_kwargs: object) -> object:
            msg = "connection refused"
            raise RuntimeError(msg)

    agent = eval_module._CountingAgent(_Failing())  # noqa: SLF001

    with pytest.raises(RuntimeError, match="connection refused"):
        asyncio.run(agent.run("chunk"))

    # Re-raised so the extractor still behaves as it does in production, but
    # counted so the report can say the comparison is not fair.
    assert agent.calls == 1
    assert agent.failures == 1
