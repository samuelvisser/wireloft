from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import YamlConfigSettingsSource

from config.config import PROJECT_ROOT
from config.settings.base import SettingsBase, normalize_settings_source_keys
from config.settings.submodels import *


class _AliasNormalizingYamlSource(YamlConfigSettingsSource):
    def __call__(self):
        return normalize_settings_source_keys(super().__call__(), self.settings_cls)


class AppSettings(SettingsBase):

    app_version: str = Field(default="0.1.0", frozen=True)

    database_path: Path = PROJECT_ROOT / "config" / "wireloft.db"

    @computed_field
    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    log_level: str = "INFO"
    timezone: str = Field(default=os.environ.get("TZ", "UTC"), description="Application timezone")

    crypto: CryptoSettings = Field(default=CryptoSettings(
        default_secret_file=PROJECT_ROOT / "data" / "wl_secret.key"
    ))
    login_session: SessionSettings = Field(default=SessionSettings(
        ttl_seconds=60 * 60 * 24 * 30
    ))
    admin_auth: AdminAuthSettings = Field(default_factory=AdminAuthSettings)
    dw_api: DailyWireAPISettings = Field(default=DailyWireAPISettings(
        middleware_api="https://middleware-prod.dailywire.com/middleware",
        stream_api="https://stream.media.dailywire.com",
    ))
    dw_oauth: OAuthSettings = Field(default=OAuthSettings(
        issuer="https://authorize.dailywire.com",
        audience="https://api.dailywire.com/",
        client_id="FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE",
        scope="openid profile offline_access",
    ))
    dw_timeout: TimeoutSettings = Field(default=TimeoutSettings(
        min_fast_request_ms=100,
        max_fast_requests=350,
        min_slow_request_ms=int(1.000 * 60 * 2),
    ))
    scheduler: SchedulerSettings = Field(default=SchedulerSettings(
        enabled=True,
        max_workers=5,
        default_max_retries=3,
        retry_backoff_seconds=5.0,
    ))
    new_episode_schedule: TrackNewEpisodeSchedule = Field(default=TrackNewEpisodeSchedule(
        find_episodes_cron="*/30 * * * *",
        monitor_episode_cron="*/1 * * * *",
        check_no_show_today_cron="0 */6 * * *",
    ))
    episode_status_timing: EpisodeStatusTiming = Field(default=EpisodeStatusTiming(
        published_countdown_after_minutes=20,
        published_final_after_minutes=3 * 60
    ))
    download_settings: DownloadSettings = Field(default=DownloadSettings(
        verify_downloads_cron="0 */2 * * *",
        max_concurrent_downloads=5,
        max_download_attempts=3,
        download_timeout_seconds=600,
        download_root=PROJECT_ROOT / "downloads",
        ascii_only_filenames=True,
        remux_video_to_mp4=True,
        ffmpeg_path="ffmpeg",
    ))
    file_watcher: FileWatcherSettings = Field(default=FileWatcherSettings(
        enabled=True,
        scan_cron="*/10 * * * *",
        verify_file_size=True,
    ))

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # kwargs > environment > .env > config.yml > file secrets > defaults
        yaml_source = _AliasNormalizingYamlSource(settings_cls)

        def normalized(source):
            return lambda: normalize_settings_source_keys(source(), settings_cls)

        return (
            normalized(init_settings),
            normalized(env_settings),
            normalized(dotenv_settings),
            yaml_source,
            normalized(file_secret_settings),
        )
