from __future__ import annotations

import typing

from pydantic_settings import PydanticBaseSettingsSource, YamlConfigSettingsSource

from ntk.models.base import CustomBaseSettings, get_env_file

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest


class DummySettings(CustomBaseSettings):
    value: str = "default"


def test_get_env_file_uses_env_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setenv("NTK_CONFIG_FILE", str(env_path))
    assert get_env_file() == env_path


def test_get_env_file_defaults_to_cwd_config_ini(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("NTK_CONFIG_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    assert get_env_file() == tmp_path / ".env"


def test_settings_customise_sources_returns_ordered_sources() -> None:
    sources = CustomBaseSettings.settings_customise_sources(
        CustomBaseSettings,
        init_settings=typing.cast("PydanticBaseSettingsSource", "init"),
        env_settings=typing.cast("PydanticBaseSettingsSource", "env"),
        dotenv_settings=typing.cast("PydanticBaseSettingsSource", "dot"),
        file_secret_settings=typing.cast("PydanticBaseSettingsSource", "secret"),
    )

    assert sources[0] == "init"
    assert sources[1] == "env"
    assert sources[2] == "dot"
    assert isinstance(sources[3], YamlConfigSettingsSource)
    assert sources[4] == "secret"


def test_custom_base_settings_follows_env_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("NUTRITION_CONFIG_FILE", raising=False)
    monkeypatch.chdir(tmp_path)

    (tmp_path / ".env").write_text("VALUE=from_envfile\n")
    (tmp_path / "config.yaml").write_text("value: from_yaml\n")
    monkeypatch.setenv("VALUE", "from_env")

    class PrioritySettings(CustomBaseSettings):
        value: str = "default"

    settings = PrioritySettings()

    assert settings.value == "from_env"
