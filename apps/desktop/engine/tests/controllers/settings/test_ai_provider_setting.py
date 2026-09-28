from __future__ import annotations

import argparse

import pytest
from sqlmodel import Session

from engine.controllers.settings.update import (
    SettingsUpdateController,
    SettingsUpdateOptions,
)
from engine.database.bootstrap import upgrade_database
from engine.database.db import create_database_engine
from engine.models.ai import AIProvider
from engine.services.ai import controller as ai_controller


def _session() -> Session:
    database = create_database_engine("sqlite://")
    upgrade_database(database)
    return Session(database)


def test_local_ai_is_the_default_provider() -> None:
    with _session() as session:
        output = SettingsUpdateController(session).run(SettingsUpdateOptions())

    assert output.result.settings.ai_provider is AIProvider.LOCAL


@pytest.mark.parametrize("kind", list(AIProvider))
def test_the_provider_is_chosen_explicitly(kind: AIProvider) -> None:
    with _session() as session:
        output = SettingsUpdateController(session).run(
            SettingsUpdateOptions(ai_provider=kind),
        )

    assert output.result.settings.ai_provider is kind


def test_the_cli_offers_exactly_the_two_providers() -> None:
    parser = argparse.ArgumentParser()
    SettingsUpdateController().add_arguments(parser)

    assert parser.parse_args(["--ai-provider", "local"]).ai_provider is AIProvider.LOCAL
    assert (
        parser.parse_args(["--ai-provider", "openai"]).ai_provider is AIProvider.OPENAI
    )
    for removed in ("ollama", "anthropic"):
        with pytest.raises(SystemExit):
            parser.parse_args(["--ai-provider", removed])
    assert "--use-cloud-model" not in parser.format_help()


def test_selected_provider_reads_the_stored_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    SettingsUpdateController(session).run(
        SettingsUpdateOptions(ai_provider=AIProvider.OPENAI),
    )
    monkeypatch.setattr(
        ai_controller,
        "settings_session",
        _reuse(session),
    )

    assert ai_controller.selected_provider() is AIProvider.OPENAI


def _reuse(session: Session):  # noqa: ANN202
    import contextlib  # noqa: PLC0415

    @contextlib.contextmanager
    def factory(_session: object):  # noqa: ANN202
        yield session

    return factory


def test_unreadable_settings_mean_local_ai_never_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import contextlib  # noqa: PLC0415

    from sqlalchemy.exc import OperationalError  # noqa: PLC0415

    @contextlib.contextmanager
    def broken(_session: object):  # noqa: ANN202
        raise OperationalError("SELECT", {}, Exception("database is locked"))
        yield

    monkeypatch.setattr(ai_controller, "settings_session", broken)

    assert ai_controller.selected_provider() is AIProvider.LOCAL
