"""Application settings.

Precedence, highest first: explicit arguments, ``ANTAR_*`` environment
variables, ``.env``, then the YAML file named by ``ANTAR_CONFIG_FILE``
(default ``configs/antar.yaml``). A missing YAML file is not an error.

Secrets (API keys) belong in the environment or ``.env``, never in YAML that
could be committed.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from antar.backends.amd_cloud.config import AmdCloudProfile
from antar.backends.lemonade.client import DEFAULT_LEMONADE_BASE_URL

CONFIG_FILE_ENV = "ANTAR_CONFIG_FILE"
DEFAULT_CONFIG_FILE = "configs/antar.yaml"


class LemonadeSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: HttpUrl = Field(
        default=HttpUrl(DEFAULT_LEMONADE_BASE_URL),
        description="Lemonade API base URL including the /v1 prefix.",
    )
    api_key: SecretStr | None = Field(
        default=None, description="Matches the server's LEMONADE_API_KEY, if one is set."
    )
    timeout_seconds: float = Field(default=3.0, gt=0, le=60)

    @field_validator("base_url")
    @classmethod
    def _no_embedded_credentials(cls, value: HttpUrl) -> HttpUrl:
        # The URL is shown in the API and dashboard, so it must not carry secrets.
        if value.username or value.password:
            raise ValueError("base_url must not contain credentials; use api_key instead")
        return value


class StorageSettings(BaseModel):
    """Local filesystem locations. All are created lazily, on first write."""

    model_config = ConfigDict(frozen=True)

    models_dir: Path = Path("data/models")
    artifacts_dir: Path = Path("data/artifacts")
    training_dir: Path = Path("data/training")
    benchmarks_dir: Path = Path("data/benchmarks")
    experiments_dir: Path = Path("data/experiments")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANTAR_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    enable_mock_backend: bool = True
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    lemonade: LemonadeSettings = LemonadeSettings()
    amd_cloud: AmdCloudProfile | None = None
    storage: StorageSettings = StorageSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_file = os.environ.get(CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
