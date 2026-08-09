"""Base Model will be pydantic class that grabs default values from environment."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


def get_env_file() -> Path:
    """Get path to env file."""
    env_file = os.getenv("NTK_CONFIG_FILE", None)
    if env_file is not None:
        return Path(env_file)
    return Path().cwd() / ".env"


class CustomBaseSettings(BaseSettings):
    """Base Model used for Controller options."""

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
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


class ConsoleRenderableModel(BaseModel, ABC):
    """Base model for responses that can be rendered to the console."""

    @abstractmethod
    def to_console(self) -> str:
        """Return a human-readable console representation."""
        raise NotImplementedError
