from __future__ import annotations

from pathlib import Path
import tomllib
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import YamlConfigSettingsSource

from config.config import PROJECT_ROOT
from config.settings.base import SettingsBase, normalize_settings_source_keys
from config.settings.cron_validation import validate_worker_cron_settings
from config.settings.submodels import *


TIMEZONE_ENVIRONMENT_VARIABLE = "TZ"
_ENVIRONMENT_VALUE_MISSING = object()


def get_app_version() -> str:
    manifest = PROJECT_ROOT / "pyproject.toml"
    try:
        with manifest.open("rb") as file:
            version = tomllib.load(file).get("project", {}).get("version")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"Could not read WireLoft version from {manifest}") from exc

    if not isinstance(version, str) or not version:
        raise RuntimeError(f"WireLoft version is missing from {manifest}")
    return version


class _AliasNormalizingYamlSource(YamlConfigSettingsSource):
    def __call__(self):
        return normalize_settings_source_keys(super().__call__(), self.settings_cls)


def _environment_value(source, name: str) -> Any:
    """Read one variable from an environment or dotenv settings source."""
    for key, value in getattr(source, "env_vars", {}).items():
        if str(key).casefold() == name.casefold():
            return value
    return _ENVIRONMENT_VALUE_MISSING


def environment_settings_source_data(source, settings_cls) -> dict[str, Any]:
    """Return normalized environment settings with WireLoft's TZ exception."""
    data = normalize_settings_source_keys(source(), settings_cls)

    # EnvSettingsSource exposes WL_TIMEZONE as ``timezone``. DotEnvSettingsSource
    # can additionally pass an unrecognised TZ key through as ``tz``/``TZ``.
    # Neither should survive before the canonical TZ value is inserted below.
    for key in ("timezone", "tz", "TZ"):
        data.pop(key, None)

    timezone = _environment_value(source, TIMEZONE_ENVIRONMENT_VARIABLE)
    if timezone is not _ENVIRONMENT_VALUE_MISSING:
        data["timezone"] = timezone

    return data


class AppSettings(SettingsBase):

    app_version: str = Field(default_factory=get_app_version, frozen=True)

    database_path: Path = PROJECT_ROOT / "config" / "wireloft.db"

    @computed_field
    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    timezone: str = Field(default="UTC", min_length=1, description="Application timezone")

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
    movie_metadata: MovieMetadataSettings = Field(default_factory=MovieMetadataSettings)
    dw_oauth: OAuthSettings = Field(default=OAuthSettings(
        issuer="https://authorize.dailywire.com",
        audience="https://api.dailywire.com/",
        client_id="FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE",
        scope="openid profile offline_access",
    ))
    dw_timeout: TimeoutSettings = Field(default=TimeoutSettings(
        min_fast_request_ms=100,
        max_fast_requests=350,
        min_slow_request_ms=int(2 * 60 * 1_000),
    ))
    scheduler: SchedulerSettings = Field(default=SchedulerSettings(
        enabled=True,
        max_workers=5,
        stalled_task_timeout_minutes=20,
        default_max_retries=3,
        retry_backoff_seconds=5.0,
    ))
    new_episode_schedule: TrackNewEpisodeSchedule = Field(default=TrackNewEpisodeSchedule(
        find_episodes_cron="*/30 * * * *",
        monitor_episode_cron="*/2 * * * *",
        check_no_show_today_cron="0 */6 * * *",
        metadata_refresh_intervals="5m,15m,30m,1h,3h,6h,24h",
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
        filename_restriction_mode=FilenameRestrictionMode.WINDOWS,
        remux_video_to_mp4=True,
        ffmpeg_path="ffmpeg",
    ))
    file_watcher: FileWatcherSettings = Field(default=FileWatcherSettings(
        enabled=True,
        scan_cron="*/10 * * * *",
        verify_file_size=True,
    ))

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any):
        return str(value).upper()

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str):
        value = value.strip()
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError(
                "Must be a valid IANA timezone, such as Europe/Amsterdam"
            ) from exc
        return value

    @model_validator(mode="after")
    def _validate_worker_cron_minimums(self):
        validate_worker_cron_settings(
            min_slow_request_ms=self.dw_timeout.min_slow_request_ms,
            find_episodes_cron=self.new_episode_schedule.find_episodes_cron,
            monitor_episode_cron=self.new_episode_schedule.monitor_episode_cron,
            check_no_show_today_cron=self.new_episode_schedule.check_no_show_today_cron,
            verify_downloads_cron=self.download_settings.verify_downloads_cron,
            file_watcher_scan_cron=self.file_watcher.scan_cron,
        )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # kwargs > environment (WL_* plus TZ) > .env > config.yml > file secrets > defaults
        yaml_source = _AliasNormalizingYamlSource(settings_cls)

        def normalized(source):
            return lambda: normalize_settings_source_keys(source(), settings_cls)

        def normalized_environment(source):
            return lambda: environment_settings_source_data(source, settings_cls)

        return (
            normalized(init_settings),
            normalized_environment(env_settings),
            normalized_environment(dotenv_settings),
            yaml_source,
            normalized(file_secret_settings),
        )
