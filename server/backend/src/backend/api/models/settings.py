from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

from backend.api.models.base import RequestBase, ResponseBase
from dailywire_downloader.storage import FilesystemStorageKind
from config.settings.cron_validation import (
    CronExpressionError,
    WorkerCronExpressionError,
    validate_cron_expression,
    worker_cron_specs,
    worker_cron_validation_errors,
)
from config.settings.settings import AppSettings
from config.settings.submodels import (
    DownloadMode,
    FilenameRestrictionMode,
    MetadataMode,
    ShowArtworkFallbackFormat,
    ThumbnailMode,
    normalize_metadata_refresh_intervals,
)


SettingFieldPath = Literal[
    "logLevel",
    "timezone",
    "crypto.secretKeyFile",
    "crypto.defaultSecretFile",
    "loginSession.ttlSeconds",
    "dwApi.middlewareApi",
    "dwApi.streamApi",
    "movieMetadata.tmdbReadAccessToken",
    "movieMetadata.tmdbApiBaseUrl",
    "movieMetadata.language",
    "movieMetadata.requestTimeoutSeconds",
    "movieMetadata.maxRetries",
    "dwOauth.issuer",
    "dwOauth.audience",
    "dwOauth.clientId",
    "dwOauth.scope",
    "dwTimeout.minFastRequestMs",
    "dwTimeout.maxFastRequests",
    "dwTimeout.minSlowRequestMs",
    "scheduler.enabled",
    "scheduler.maxWorkers",
    "scheduler.stalledTaskTimeoutMinutes",
    "scheduler.defaultMaxRetries",
    "scheduler.retryBackoffSeconds",
    "newEpisodeSchedule.findEpisodesCronEnabled",
    "newEpisodeSchedule.findEpisodesCron",
    "newEpisodeSchedule.monitorPendingEpisodeCronEnabled",
    "newEpisodeSchedule.monitorPendingEpisodeCron",
    "newEpisodeSchedule.monitorNoUsableMediaEpisodeCronEnabled",
    "newEpisodeSchedule.monitorNoUsableMediaEpisodeCron",
    "newEpisodeSchedule.metadataRefreshIntervals",
    "episodeStatusTiming.publishedFinalAfterMinutes",
    "episodeStatusTiming.dwProcessingMaxMinutes",
    "episodeStatusTiming.noUsableMediaDeleteAfterMinutes",
    "downloadSettings.verifyDownloadsCronEnabled",
    "downloadSettings.verifyDownloadsCron",
    "downloadSettings.maxConcurrentDownloads",
    "downloadSettings.maxDownloadAttempts",
    "downloadSettings.downloadTimeoutSeconds",
    "downloadSettings.downloadRoot",
    "downloadSettings.downloadMode",
    "downloadSettings.thumbnailMode",
    "downloadSettings.metadataMode",
    "downloadSettings.downloadShowAssets",
    "downloadSettings.showArtworkFallbackFormat",
    "downloadSettings.temporaryDownloadRoot",
    "downloadSettings.rssCacheRoot",
    "downloadSettings.rssCacheRetentionSeconds",
    "downloadSettings.filenameRestrictionMode",
    "downloadSettings.remuxVideoToMp4",
    "downloadSettings.ffmpegPath",
    "fileWatcher.enabled",
    "fileWatcher.scanCronEnabled",
    "fileWatcher.scanCron",
    "fileWatcher.verifyFileSize",
]

UI_SETTING_PATHS: tuple[SettingFieldPath, ...] = (
    "logLevel",
    "timezone",
    "crypto.secretKeyFile",
    "crypto.defaultSecretFile",
    "loginSession.ttlSeconds",
    "dwApi.middlewareApi",
    "dwApi.streamApi",
    "movieMetadata.tmdbReadAccessToken",
    "movieMetadata.tmdbApiBaseUrl",
    "movieMetadata.language",
    "movieMetadata.requestTimeoutSeconds",
    "movieMetadata.maxRetries",
    "dwOauth.issuer",
    "dwOauth.audience",
    "dwOauth.clientId",
    "dwOauth.scope",
    "dwTimeout.minFastRequestMs",
    "dwTimeout.maxFastRequests",
    "dwTimeout.minSlowRequestMs",
    "scheduler.enabled",
    "scheduler.maxWorkers",
    "scheduler.stalledTaskTimeoutMinutes",
    "scheduler.defaultMaxRetries",
    "scheduler.retryBackoffSeconds",
    "newEpisodeSchedule.findEpisodesCronEnabled",
    "newEpisodeSchedule.findEpisodesCron",
    "newEpisodeSchedule.monitorPendingEpisodeCronEnabled",
    "newEpisodeSchedule.monitorPendingEpisodeCron",
    "newEpisodeSchedule.monitorNoUsableMediaEpisodeCronEnabled",
    "newEpisodeSchedule.monitorNoUsableMediaEpisodeCron",
    "newEpisodeSchedule.metadataRefreshIntervals",
    "episodeStatusTiming.publishedFinalAfterMinutes",
    "episodeStatusTiming.dwProcessingMaxMinutes",
    "episodeStatusTiming.noUsableMediaDeleteAfterMinutes",
    "downloadSettings.verifyDownloadsCronEnabled",
    "downloadSettings.verifyDownloadsCron",
    "downloadSettings.maxConcurrentDownloads",
    "downloadSettings.maxDownloadAttempts",
    "downloadSettings.downloadTimeoutSeconds",
    "downloadSettings.downloadRoot",
    "downloadSettings.downloadMode",
    "downloadSettings.thumbnailMode",
    "downloadSettings.metadataMode",
    "downloadSettings.downloadShowAssets",
    "downloadSettings.temporaryDownloadRoot",
    "downloadSettings.rssCacheRoot",
    "downloadSettings.rssCacheRetentionSeconds",
    "downloadSettings.filenameRestrictionMode",
    "downloadSettings.remuxVideoToMp4",
    "downloadSettings.ffmpegPath",
    "fileWatcher.enabled",
    "fileWatcher.scanCronEnabled",
    "fileWatcher.scanCron",
    "fileWatcher.verifyFileSize",
)


class _SettingsValueModel(BaseModel):
    """Strict, camelCase API model for settings that may be changed in the UI."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


def _validate_http_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ValueError("Enter a complete http:// or https:// URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a complete http:// or https:// URL")
    return value


def _validate_non_empty_path(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        raise ValueError("Path cannot be empty")
    return value


def _api_setting_path(path: tuple[str, ...]) -> str:
    return ".".join(to_camel(segment) for segment in path)


class CryptoFileSettingsValue(_SettingsValueModel):
    """Safe crypto settings; literal secret material is deliberately excluded."""

    secret_key_file: Path | None = None
    default_secret_file: Path

    _validate_secret_key_file = field_validator(
        "secret_key_file", mode="before"
    )(_validate_non_empty_path)
    _validate_default_secret_file = field_validator(
        "default_secret_file", mode="before"
    )(_validate_non_empty_path)


class SessionSettingsValue(_SettingsValueModel):
    ttl_seconds: int = Field(ge=60)


class DailyWireAPISettingsValue(_SettingsValueModel):
    middleware_api: str = Field(min_length=1)
    stream_api: str = Field(min_length=1)

    _validate_middleware_api = field_validator("middleware_api")(_validate_http_url)
    _validate_stream_api = field_validator("stream_api")(_validate_http_url)


class MovieMetadataSettingsValue(_SettingsValueModel):
    """TMDB settings with the token represented as a write-only replacement value."""

    tmdb_read_access_token: str = ""
    tmdb_read_access_token_configured: bool = False
    tmdb_api_base_url: str = Field(min_length=1)
    language: str = Field(min_length=1)
    request_timeout_seconds: float = Field(ge=1)
    max_retries: int = Field(ge=0, le=5)

    _validate_tmdb_api_base_url = field_validator("tmdb_api_base_url")(_validate_http_url)


class OAuthSettingsValue(_SettingsValueModel):
    issuer: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)

    _validate_issuer = field_validator("issuer")(_validate_http_url)
    _validate_audience = field_validator("audience")(_validate_http_url)


class TimeoutSettingsValue(_SettingsValueModel):
    min_fast_request_ms: int = Field(ge=0)
    max_fast_requests: int = Field(ge=1)
    min_slow_request_ms: int = Field(ge=0)


class SchedulerSettingsValue(_SettingsValueModel):
    enabled: bool
    max_workers: int = Field(ge=1)
    stalled_task_timeout_minutes: int = Field(ge=1)
    default_max_retries: int = Field(ge=0)
    retry_backoff_seconds: float = Field(ge=0)


class TrackNewEpisodeScheduleValue(_SettingsValueModel):
    find_episodes_cron_enabled: bool
    find_episodes_cron: str = Field(min_length=1)
    monitor_pending_episode_cron_enabled: bool
    monitor_pending_episode_cron: str = Field(min_length=1)
    monitor_no_usable_media_episode_cron_enabled: bool
    monitor_no_usable_media_episode_cron: str = Field(min_length=1)
    metadata_refresh_intervals: str = Field(min_length=1)

    _validate_metadata_refresh_intervals = field_validator(
        "metadata_refresh_intervals"
    )(normalize_metadata_refresh_intervals)


class EpisodeStatusTimingValue(_SettingsValueModel):
    published_final_after_minutes: int = Field(ge=0)
    dw_processing_max_minutes: int = Field(ge=0)
    no_usable_media_delete_after_minutes: int = Field(ge=0)


class DownloadSettingsValue(_SettingsValueModel):
    verify_downloads_cron_enabled: bool
    verify_downloads_cron: str = Field(min_length=1)
    max_concurrent_downloads: int = Field(ge=1)
    max_download_attempts: int = Field(ge=1)
    download_timeout_seconds: int = Field(ge=1)
    download_root: Path
    download_mode: DownloadMode
    thumbnail_mode: ThumbnailMode
    metadata_mode: MetadataMode
    download_show_assets: bool
    show_artwork_fallback_format: ShowArtworkFallbackFormat
    temporary_download_root: Path
    rss_cache_root: Path
    rss_cache_retention_seconds: int = Field(ge=1)
    filename_restriction_mode: FilenameRestrictionMode
    remux_video_to_mp4: bool
    ffmpeg_path: str = Field(min_length=1)

    _validate_download_root = field_validator(
        "download_root", mode="before"
    )(_validate_non_empty_path)
    _validate_temporary_download_root = field_validator(
        "temporary_download_root", mode="before"
    )(_validate_non_empty_path)
    _validate_rss_cache_root = field_validator(
        "rss_cache_root", mode="before"
    )(_validate_non_empty_path)


class FileWatcherSettingsValue(_SettingsValueModel):
    enabled: bool
    scan_cron_enabled: bool
    scan_cron: str = Field(min_length=1)
    verify_file_size: bool



class SettingsValues(_SettingsValueModel):
    """Every application setting intentionally exposed by the Settings UI.

    Literal crypto secret material and the stored TMDB token are deliberately
    absent from responses. The TMDB token field is always blank when reading
    settings and acts only as a replacement value when saving.
    """

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    timezone: str = Field(min_length=1)
    crypto: CryptoFileSettingsValue
    login_session: SessionSettingsValue
    dw_api: DailyWireAPISettingsValue
    movie_metadata: MovieMetadataSettingsValue
    dw_oauth: OAuthSettingsValue
    dw_timeout: TimeoutSettingsValue
    scheduler: SchedulerSettingsValue
    new_episode_schedule: TrackNewEpisodeScheduleValue
    episode_status_timing: EpisodeStatusTimingValue
    download_settings: DownloadSettingsValue
    file_watcher: FileWatcherSettingsValue

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any):
        return str(value).upper()

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Enter a valid IANA timezone, such as Europe/Amsterdam") from exc
        return value

    @classmethod
    def from_app_settings(cls, settings: AppSettings) -> "SettingsValues":
        tmdb_token = settings.movie_metadata.tmdb_read_access_token
        return cls(
            log_level=settings.log_level,
            timezone=settings.timezone,
            crypto=CryptoFileSettingsValue.model_validate(settings.crypto),
            login_session=SessionSettingsValue.model_validate(settings.login_session),
            dw_api=DailyWireAPISettingsValue.model_validate(settings.dw_api),
            movie_metadata=MovieMetadataSettingsValue(
                tmdb_read_access_token="",
                tmdb_read_access_token_configured=bool(
                    tmdb_token and tmdb_token.get_secret_value().strip()
                ),
                tmdb_api_base_url=settings.movie_metadata.tmdb_api_base_url,
                language=settings.movie_metadata.language,
                request_timeout_seconds=settings.movie_metadata.request_timeout_seconds,
                max_retries=settings.movie_metadata.max_retries,
            ),
            dw_oauth=OAuthSettingsValue.model_validate(settings.dw_oauth),
            dw_timeout=TimeoutSettingsValue.model_validate(settings.dw_timeout),
            scheduler=SchedulerSettingsValue.model_validate(settings.scheduler),
            new_episode_schedule=TrackNewEpisodeScheduleValue.model_validate(settings.new_episode_schedule),
            episode_status_timing=EpisodeStatusTimingValue.model_validate(settings.episode_status_timing),
            download_settings=DownloadSettingsValue.model_validate(settings.download_settings),
            file_watcher=FileWatcherSettingsValue.model_validate(settings.file_watcher),
        )

    def to_config_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


class SettingsAPIUpdate(RequestBase):
    values: SettingsValues
    changed_fields: list[SettingFieldPath] = Field(min_length=1)

    @field_validator("changed_fields")
    @classmethod
    def _changed_fields_must_be_unique(cls, values: list[SettingFieldPath]):
        if len(values) != len(set(values)):
            raise ValueError("changedFields must not contain duplicates")
        return values

    @model_validator(mode="after")
    def _validate_worker_crons(self):
        changed = set(self.changed_fields)
        validate_all_intervals = "dwTimeout.minSlowRequestMs" in changed
        specs = worker_cron_specs(self.values)
        specs_by_path = {spec.field_path: spec for spec in specs}

        line_errors = []
        invalid_changed_fields: set[str] = set()
        for spec in specs:
            field = _api_setting_path(spec.field_path)
            if field not in changed:
                continue
            try:
                validate_cron_expression(spec.expression)
            except CronExpressionError:
                invalid_changed_fields.add(field)
                line_errors.append({
                    "type": PydanticCustomError(
                        "cron_expression_invalid",
                        "{message}",
                        {"message": "Enter a valid five-part cron expression"},
                    ),
                    "loc": ("values", *field.split(".")),
                    "input": spec.expression,
                })

        policy_errors = worker_cron_validation_errors(self.values)

        for error in policy_errors:
            spec = specs_by_path[error.field_path]
            field = _api_setting_path(spec.field_path)
            if field in invalid_changed_fields:
                continue

            directly_affected = (
                field in changed
                or _api_setting_path(spec.enabled_field_path) in changed
            )
            if isinstance(error, WorkerCronExpressionError):
                if not directly_affected:
                    continue
                error_type = PydanticCustomError(
                    "cron_expression_invalid",
                    "{message}",
                    {"message": str(error)},
                )
            else:
                if not validate_all_intervals and not directly_affected:
                    continue
                error_type = PydanticCustomError(
                    "worker_cron_interval_too_short",
                    "{message}",
                    {"message": str(error)},
                )

            value: Any = self.values
            for segment in error.field_path:
                value = getattr(value, segment)
            line_errors.append({
                "type": error_type,
                "loc": ("values", *field.split(".")),
                "input": value,
            })

        if line_errors:
            raise ValidationError.from_exception_data(
                self.__class__.__name__,
                line_errors,
            )
        return self


class SettingsValidationIssueValue(ResponseBase):
    field: SettingFieldPath
    code: Literal["cron_expression_invalid", "worker_cron_interval_too_short"]
    message: str
    source: str


class FilesystemInspectionValue(ResponseBase):
    path: str
    mount_point: str | None = None
    filesystem_type: str | None = None
    storage_kind: FilesystemStorageKind


class DownloadStorageInspectionValue(ResponseBase):
    download_root: FilesystemInspectionValue
    temporary_download_root: FilesystemInspectionValue
    same_filesystem: bool | None = None


class SettingsAPIRead(ResponseBase):
    values: SettingsValues
    configured_fields: list[SettingFieldPath]
    environment_overrides: dict[str, str]
    download_storage: DownloadStorageInspectionValue
    validation_issues: list[SettingsValidationIssueValue] = Field(default_factory=list)
    updated_at: datetime | None = None
