"""Base Model will be pydantic class that grabs default values from environment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


def get_env_file() -> Path:
    """Get path to env file."""
    env_file = os.getenv("NUTRITION_CONFIG_FILE", None)
    if env_file is not None:
        return Path(env_file)
    return Path().cwd() / "config.ini"


class CustomBaseSettings(BaseSettings):
    """Base Model used for Controller options."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config.yaml",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Set priority that default values obtained from."""
        return (
            init_settings,  # CLI overrides
            env_settings,  # Environment variables
            dotenv_settings,  # .env
            YamlConfigSettingsSource(settings_cls),  # config.yaml
            file_secret_settings,  # Docker/K8s secrets
        )
