from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from wireloft_config.config import PROJECT_ROOT

import bcrypt  # or from argon2 import PasswordHasher


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WL_",  # e.g. WL_ADMIN_PASSWORD_HASH
        env_file=".env",  # optional: read .env in dev
        extra="ignore",
        yaml_file=Path(f"{PROJECT_ROOT}/config/config.yaml")
    )

    # --- HTTP / CORS / Cookies
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = True

    # --- Auth toggles & inputs
    # Preferred: already-hashed password
    admin_password_hash: SecretStr | None = None

    # Convenience inputs (DEV or secrets): we’ll hash one of these at startup if provided
    admin_password: SecretStr | None = None
    admin_password_file: FilePath | None = None

    # Optional pepper (extra server-side secret added before hashing/verify)
    password_pepper: SecretStr | None = None

    # Derived/normalized field: the effective hash this app will trust
    effective_admin_password_hash: SecretStr | None = Field(default=None, exclude=True)

    # Optional encryption key used elsewhere (e.g., for token store encryption)
    encryption_key: SecretStr | None = None  # e.g., a Fernet key; validate elsewhere

    # Optional path for a structured config (if you want to surface it in code/tools)
    settings_file: Path | None = None

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ):
        """
        Final order (high → low):
        1. Environment variables (env_settings)
        2. Docker secrets (file_secret_settings)
        3. Config file (our custom FileSettingsSource)
        4. .env (dotenv_settings)
        5. init kwargs (init_settings)  <-- typically least priority in server apps
        """
        return (
            env_settings,
            file_secret_settings,
            FileSettingsSource(cls),
            dotenv_settings,
            init_settings,
        )









    @property
    def auth_enabled(self) -> bool:
        return self.effective_admin_password_hash is not None

    # Post-processing: compute a single effective hash and drop plaintext
    @model_validator(mode="after")
    def _finalize_auth(cls, values: "AppConfig"):
        # If a hash is provided, use it; else hash plaintext from file/env exactly once.
        if values.admin_password_hash:
            values.effective_admin_password_hash = values.admin_password_hash
        else:
             if values.admin_password_file:
                raw = Path(values.admin_password_file).read_text(encoding="utf-8").strip()
            elif values.admin_password:
                raw = values.admin_password.get_secret_value()

            if raw:
                # Add optional pepper
                pepper = values.password_pepper.get_secret_value() if values.password_pepper else ""
                pw = (raw + pepper).encode("utf-8")
                # bcrypt hash (argon2id works too; pick one and stick with it)
                hashed = bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("utf-8")
                values.effective_admin_password_hash = SecretStr(hashed)

        # Scrub plaintext from the settings object ASAP
        values.admin_password = None
        return values

    # Helper used by your auth layer
    def verify_admin_password(self, candidate: str) -> bool:
        if not self.auth_enabled:
            return True  # open mode
        pepper = self.password_pepper.get_secret_value() if self.password_pepper else ""
        candidate_bytes = (candidate + pepper).encode("utf-8")
        stored = self.effective_admin_password_hash.get_secret_value().encode("utf-8")
        try:
            return bcrypt.checkpw(candidate_bytes, stored)
        except Exception:
            return False


class ShowConfig(BaseModel):
    name: str
    url: Optional[str] = None
    start_date: Optional[date] = None
    audio_only: Optional[bool] = None
    filters: Optional[Dict[str, Any]] = None


class Settings(BaseModel):
    # Global defaults (can be overridden by YAML or environment)
    schedule: str = Field(default="*/15 * * * *", description="Cron schedule for the app controller")

    # Common paths
    download_dir: Path = Field(default=Path("/downloads"), description="Base directory for downloads")
    data_dir: Path = Field(default=Path("data"), description="Data directory under project root")
    database_path: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "wireloft.db", description="Path to SQLite DB")

    # Specific DailyWire related URLs (expose defaults used in dailywire_api)
    middleware_api: str = Field(default="https://middleware-prod.dailywire.com/middleware", description="DailyWire Middleware base URL")
    stream_api: str = Field(default="https://stream.media.dailywire.com", description="DailyWire Stream base URL")


class AppConfig(BaseSettings, Settings):
    """Application settings loaded from defaults, YAML config, and environment.

    Precedence (lowest to highest):
      1) Built-in defaults (defined in fields)
      2) config.yml from project root (or config/config.yml), or path in WL_CONFIG_FILE
      3) Environment variables (prefix: WL_)
    """

    # Configure environment handling
    model_config = SettingsConfigDict(
        env_prefix="WL_",
        env_nested_delimiter="__",  # e.g. WL_shows__0__name
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def _yaml_settings_source(cls) -> PydanticBaseSettingsSource:
        # Factory producing a settings source callable
        def source(settings: BaseSettings) -> Dict[str, Any]:
            # 1) Allow an explicit path via env var
            env_path = os.getenv("WL_CONFIG_FILE")
            candidate_paths: List[Path] = []
            if env_path:
                candidate_paths.append(Path(env_path))
            candidate_paths.extend(possible_config_paths(find_project_root()))

            for path in candidate_paths:
                try:
                    if path.is_file():
                        with path.open("r", encoding="utf-8") as f:
                            loaded = yaml.safe_load(f) or {}
                        if not isinstance(loaded, dict):
                            return {}
                        # Normalize some known keys to match our field names
                        # For example, allow "schedule", "start_date", etc. directly.
                        return loaded
                except FileNotFoundError:
                    continue
                except Exception:
                    # On parse or IO error, fall back silently to defaults
                    return {}
            return {}

        return source  # type: ignore[return-value]

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls,
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = cls._yaml_settings_source()
        # Precedence: init (kwargs) -> YAML -> env -> dotenv -> secrets
        return (
            init_settings,
            yaml_source,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )
