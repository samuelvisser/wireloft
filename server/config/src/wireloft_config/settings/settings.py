from __future__ import annotations

from pathlib import Path

from pydantic_settings import YamlConfigSettingsSource

from wireloft_config.config import PROJECT_ROOT
from wireloft_config.settings.base import SettingsBase
from wireloft_config.settings.submodels import *


class AppSettings(SettingsBase):

    app_version: str = Field(default="0.1.0", frozen=True)

    schedule: str = "*/15 * * * *"
    database_path: Path = PROJECT_ROOT / "data" / "wireloft.db"
    log_level: str = "INFO"

    crypto: CryptoSettings = Field(default_factory=CryptoSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    admin_auth: AdminAuthSettings = Field(default_factory=AdminAuthSettings)
    dw_oauth: OAuthSettings = Field(default_factory=OAuthSettings)
    dw_timeout: TimeoutSettings = Field(default_factory=TimeoutSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        # kwargs > env > .env > YAML > file secrets > defaults
        yaml_source = YamlConfigSettingsSource(settings_cls)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_source,
            file_secret_settings,
        )
