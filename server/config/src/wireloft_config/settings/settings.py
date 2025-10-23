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
    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"
    log_level: str = "INFO"
    timezone: str = Field(default="UTC", description="Application timezone")
    final_ep_published_delay_minutes: int = Field(default=3 * 60, description="Delay in minutes before we can safely assume the episode's published status is final")

    crypto: CryptoSettings = Field(default_factory=lambda: CryptoSettings(
        default_secret_file=PROJECT_ROOT / "data" / "wl_secret.key"
    ))
    session: SessionSettings = Field(default_factory=lambda: SessionSettings(
        ttl_seconds=60 * 60 * 24 * 30                   # 30 days
    ))
    admin_auth: AdminAuthSettings = Field(default_factory=AdminAuthSettings)
    dw_api: DailyWireAPISettings = Field(default_factory=lambda: DailyWireAPISettings(
        middleware_api="https://middleware-prod.dailywire.com/middleware",
        stream_api="https://stream.media.dailywire.com",
    ))
    dw_oauth: OAuthSettings = Field(default_factory=lambda: OAuthSettings(
        issuer="https://authorize.dailywire.com",
        audience="https://api.dailywire.com/",
        client_id="FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE",
        scope="openid profile offline_access",
    ))
    dw_timeout: TimeoutSettings = Field(default_factory=lambda: TimeoutSettings(
        min_fast_request_ms=100,
        max_fast_requests=350,
        min_slow_request_ms=int(1.000 * 60 * 2),        # 2 minutes
    ))
    scheduler: SchedulerSettings = Field(default_factory=lambda: SchedulerSettings(
        enabled=True,
        max_workers=5,
        default_max_retries=3,
        retry_backoff_seconds=5.0,
    ))

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
