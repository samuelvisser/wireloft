import os
from enum import StrEnum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from pydantic import Field, SecretStr, ValidationInfo, field_validator

from config.security.passwords import derive_admin_password_client_value, hash_password_scrypt
from config.settings.base import SubmodelBase


def _validate_http_url(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ValueError("Must be a complete http:// or https:// URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Must be a complete http:// or https:// URL")
    return value


def _validate_non_empty_path(value):
    if isinstance(value, str) and not value.strip():
        raise ValueError("Path cannot be empty")
    return value


class OAuthSettings(SubmodelBase):
    issuer: str = Field(..., min_length=1, description="Issuer URL for OAuth authentication")
    audience: str = Field(..., min_length=1, description="Audience URL for OAuth authentication")
    client_id: str = Field(..., min_length=1, description="Client ID for OAuth authentication")
    scope: str = Field(..., min_length=1, description="Scope for OAuth authentication")

    _validate_issuer = field_validator("issuer")(_validate_http_url)
    _validate_audience = field_validator("audience")(_validate_http_url)


class TimeoutSettings(SubmodelBase):
    min_fast_request_ms: int = Field(
        ...,
        ge=0,
        description="Minimum time in milliseconds for a fast request",
    )
    max_fast_requests: int = Field(
        ...,
        ge=1,
        description="Maximum number of fast requests allowed",
    )
    min_slow_request_ms: int = Field(
        ...,
        ge=0,
        description="Milliseconds to wait after max fast requests where made",
    )


class CryptoSettings(SubmodelBase):
    secret_key: Optional[str] = Field(default=None, description="Literal secret key material for Fernet (base64 or raw text)")
    secret_key_file: Optional[Path] = Field(default=None, description="Path to a file containing the secret key")
    default_secret_file: Path = Field(..., description="Default path if no explicit key or file is provided", frozen=True)

    _validate_secret_key_file = field_validator(
        "secret_key_file", mode="before"
    )(_validate_non_empty_path)
    _validate_default_secret_file = field_validator(
        "default_secret_file", mode="before"
    )(_validate_non_empty_path)


class SessionSettings(SubmodelBase):
    ttl_seconds: int = Field(
        ...,
        ge=60,
        description="Time in seconds the session stays valid",
    )


class DailyWireAPISettings(SubmodelBase):
    middleware_api: str = Field(..., min_length=1, description="Middleware API base URL")
    stream_api: str = Field(..., min_length=1, description="Stream API base URL")

    _validate_middleware_api = field_validator("middleware_api")(_validate_http_url)
    _validate_stream_api = field_validator("stream_api")(_validate_http_url)


class MovieMetadataSettings(SubmodelBase):
    """Third-party metadata settings used to enrich movies when first added."""

    tmdb_read_access_token: Optional[SecretStr] = Field(
        default=None,
        description="TMDB API Read Access Token used for one-time movie release-date lookups",
    )
    tmdb_api_base_url: str = Field(
        default="https://api.themoviedb.org/3",
        min_length=1,
        description="TMDB API base URL",
    )
    language: str = Field(default="en-US", min_length=1, description="TMDB metadata language")
    request_timeout_seconds: float = Field(
        default=10.0,
        ge=1,
        description="Timeout for TMDB API requests",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retries for transient TMDB API failures",
    )

    _validate_tmdb_api_base_url = field_validator("tmdb_api_base_url")(_validate_http_url)

    @field_validator("tmdb_read_access_token", mode="before")
    @classmethod
    def _normalize_tmdb_token(cls, value):
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class AdminAuthSettings(SubmodelBase):
    password_hash: Optional[str] = None

    # Ephemeral input (never dumped, never repr) – only used to get plaintext password
    password: Optional[str] = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    @property
    def enabled(self) -> bool:
        return self.password_hash is not None

    @field_validator("password", mode="before")
    @classmethod
    def _normalize_password(cls, v: Optional[str]):
        if v is None:
            return None
        if isinstance(v, str) and v.strip().lower() in ["false", "0", ""]:
            return None
        return v

    @field_validator("password_hash", mode="before")
    @classmethod
    def _normalize_password_hash(cls, value: Optional[str]):
        if value is None:
            return None
        return value.strip() or None

    @field_validator("password", mode="after")
    @classmethod
    def _finalize_password(cls, value: Optional[str], info: ValidationInfo):
        # Password hashing remains finalized by the model validator below in existing
        # deployments. This validator only keeps Pydantic's field lifecycle explicit.
        return value

    def model_post_init(self, __context) -> None:
        # If admin_password_hash already set to a scrypt hash string, keep it.
        if self.password_hash and self.password_hash.startswith("scrypt$"):
            pass
        else:
            env_hash = os.environ.get("WL_ADMIN_AUTH__PASSWORD_HASH")
            if isinstance(env_hash, str) and env_hash.startswith("scrypt$"):
                self.password_hash = env_hash
            else:
                plain = self.password or self._normalize_password(os.environ.get("WL_ADMIN_AUTH__PASSWORD"))
                if plain:
                    client_val = derive_admin_password_client_value(plain)
                    self.password_hash = hash_password_scrypt(client_val)
                    os.environ["WL_ADMIN_AUTH__PASSWORD_HASH"] = str(self.password_hash)
                else:
                    self.password_hash = None

        self.password = None
        os.environ.pop("WL_ADMIN_AUTH__PASSWORD", None)


class SchedulerSettings(SubmodelBase):
    enabled: bool = Field(..., description="Enable the internal APScheduler-based scheduler")
    max_workers: int = Field(
        ...,
        ge=1,
        description="Max concurrent jobs in the thread pool executor",
    )
    default_max_retries: int = Field(
        ...,
        ge=0,
        description="Default maximum retries per task if not specified by task or schedule",
    )
    retry_backoff_seconds: float = Field(
        ...,
        ge=0,
        description="Base seconds for exponential backoff between retries",
    )


class RepeatingTaskSettings(SubmodelBase):
    cron_schedule: str = Field(..., min_length=1, description="Cron schedule string for repeating tasks")


class TrackNewEpisodeSchedule(SubmodelBase):
    find_episodes_cron: str = Field(..., min_length=1, description="Cron schedule string for finding new episodes")
    monitor_episode_cron: str = Field(..., min_length=1, description="Cron schedule string for monitoring an episode that exists but is not yet fully published")
    check_no_show_today_cron: str = Field(..., min_length=1, description="Cron schedule string for checking whether 'No Show Today' placeholder episodes have been removed from Daily Wire")


class EpisodeStatusTiming(SubmodelBase):
    published_countdown_after_minutes: int = Field(
        ...,
        ge=0,
        description="Delay in minutes after dw reports the episode as published we can assume it actually is",
    )
    published_final_after_minutes: int = Field(
        ...,
        ge=0,
        description="Delay in minutes after dw reports the episode as published we can safely assume it no longer contains the countdown",
    )

    @field_validator("published_final_after_minutes")
    @classmethod
    def _final_must_not_precede_countdown(cls, value: int, info: ValidationInfo):
        countdown = info.data.get("published_countdown_after_minutes")
        if isinstance(countdown, int) and value < countdown:
            raise ValueError(
                "Final publication timing must be at least as long as countdown publication timing"
            )
        return value


class FilenameRestrictionMode(StrEnum):
    UNRESTRICTED = "unrestricted"
    WINDOWS = "windows"
    RESTRICTED = "restricted"


class DownloadSettings(SubmodelBase):
    verify_downloads_cron: str = Field(..., min_length=1, description="Cron schedule for verifying downloads")
    max_concurrent_downloads: int = Field(
        ...,
        ge=1,
        description="Maximum number of concurrent downloads",
    )
    max_download_attempts: int = Field(
        ...,
        ge=1,
        description="Maximum number of download attempts",
    )
    download_timeout_seconds: int = Field(
        ...,
        ge=1,
        description="Timeout in seconds for each download",
    )
    download_root: Path = Field(..., description="Directory on disk that the '/downloads/' prefix of output templates maps to")
    filename_restriction_mode: FilenameRestrictionMode = Field(
        default=FilenameRestrictionMode.WINDOWS,
        description="Filename compatibility mode: minimal restrictions, Windows-compatible, or restricted ASCII",
    )
    remux_video_to_mp4: bool = Field(
        ...,
        description="Repackage downloaded HLS video into an .mp4 file instead of leaving it as raw .ts. "
                    "This is a fast, lossless container change (no re-encoding) and requires ffmpeg to be "
                    "installed and on PATH.",
    )
    ffmpeg_path: str = Field(
        default="ffmpeg",
        min_length=1,
        description="Path to the ffmpeg binary used for remuxing video to mp4",
    )

    _validate_download_root = field_validator(
        "download_root", mode="before"
    )(_validate_non_empty_path)


class FileWatcherSettings(SubmodelBase):
    enabled: bool = Field(..., description="Enable the file watcher that keeps downloaded episode files in sync with the database")
    scan_cron: str = Field(..., min_length=1, description="Cron schedule for the periodic file watcher scan")
    verify_file_size: bool = Field(..., description="Flag a download as corrupted when its file is empty or smaller than the size recorded when it finished downloading")
