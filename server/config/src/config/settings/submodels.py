from config.security.passwords import hash_password_scrypt, derive_admin_password_client_value
from config.settings.base import SubmodelBase

from typing import Optional
from pydantic import Field, field_validator, model_validator

import os
from pathlib import Path


class OAuthSettings(SubmodelBase):
    issuer: str = Field(..., description="Issuer URL for OAuth authentication")
    audience: str = Field(..., description="Audience URL for OAuth authentication")
    client_id: str = Field(..., description="Client ID for OAuth authentication")
    scope: str = Field(..., description="Scope for OAuth authentication")


class TimeoutSettings(SubmodelBase):
    min_fast_request_ms: int = Field(..., description="Minimum time in milliseconds for a fast request")
    max_fast_requests: int = Field(..., description="Maximum number of fast requests allowed")
    min_slow_request_ms: int = Field(..., description="Milliseconds to wait after max fast requests where made")


class CryptoSettings(SubmodelBase):
    secret_key: Optional[str] = Field(default=None, description="Literal secret key material for Fernet (base64 or raw text)")
    secret_key_file: Optional[Path] = Field(default=None, description="Path to a file containing the secret key")
    default_secret_file: Path = Field(..., description="Default path if no explicit key or file is provided", frozen=True)


class SessionSettings(SubmodelBase):
    ttl_seconds: int = Field(..., description="Time in seconds the session stays valid")     # 30 days default session lifetime


class DailyWireAPISettings(SubmodelBase):
    middleware_api: str = Field(..., description="Middleware API base URL")
    stream_api: str = Field(..., description="Stream API base URL")


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

    @model_validator(mode="after")
    def _finalize_password(self):
        # If admin_password_hash already set to a scrypt hash string, keep it
        if self.password_hash and self.password_hash.startswith("scrypt$"):
            pass
        else:
            # Check env-provided precomputed hash
            env_hash = os.environ.get("WL_ADMIN_AUTH__PASSWORD_HASH")
            if isinstance(env_hash, str) and env_hash.startswith("scrypt$"):
                self.password_hash = env_hash
            else:
                # Compute from plaintext sources
                plain = self.password or self._normalize_password(os.environ.get("WL_ADMIN_AUTH__PASSWORD"))
                if plain:
                    client_val = derive_admin_password_client_value(plain)
                    self.password_hash = hash_password_scrypt(client_val)
                    os.environ["WL_ADMIN_AUTH__PASSWORD_HASH"] = str(self.password_hash)
                else:
                    self.password_hash = None

        # scrub plaintext from memory and environment
        self.password = None
        os.environ.pop("WL_ADMIN_AUTH__PASSWORD", None)

        return self


class SchedulerSettings(SubmodelBase):
    enabled: bool = Field(..., description="Enable the internal APScheduler-based scheduler")
    max_workers: int = Field(..., description="Max concurrent jobs in the thread pool executor")
    default_max_retries: int = Field(..., description="Default maximum retries per task if not specified by task or schedule")
    retry_backoff_seconds: float = Field(..., description="Base seconds for exponential backoff between retries")


class RepeatingTaskSettings(SubmodelBase):
    cron_schedule: str = Field(..., description="Cron schedule string for repeating tasks")


class TrackNewEpisodeSchedule(SubmodelBase):
    find_episodes_cron: str = Field(..., description="Cron schedule string for finding new episodes")
    monitor_episode_cron: str = Field(..., description="Cron schedule string for monitoring an episode that exists but is not yet fully published")


class EpisodeStatusTiming(SubmodelBase):
    published_countdown_after_minutes: int = Field(..., description="Delay in minutes after dw reports the episode as published we can assume it actually is")
    published_final_after_minutes: int = Field(..., description="Delay in minutes after dw reports the episode as published we can safely assume it no longer contains the countdown")


class DownloadSettings(SubmodelBase):
    verify_downloads_cron: str = Field(..., description="Cron schedule for verifying downloads")
    max_concurrent_downloads: int = Field(..., description="Maximum number of concurrent downloads")
    max_download_attempts: int = Field(..., description="Maximum number of download attempts")
    download_timeout_seconds: int = Field(..., description="Timeout in seconds for each download")
    download_root: Path = Field(..., description="Directory on disk that the '/downloads/' prefix of output templates maps to")


class FileWatcherSettings(SubmodelBase):
    enabled: bool = Field(..., description="Enable the file watcher that keeps downloaded episode files in sync with the database")
    scan_cron: str = Field(..., description="Cron schedule for the periodic file watcher scan")
    verify_file_size: bool = Field(..., description="Flag a download as corrupted when its file is empty or smaller than the size recorded when it finished downloading")
