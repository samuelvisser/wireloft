import os
from typing import Optional, Union, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import YamlConfigSettingsSource

from wireloft_config.base import SubmodelBase, SettingsBase
from wireloft_config.security.passwords import hash_password_scrypt


class _OAuthSettings(SubmodelBase):
    issuer: str
    audience: str
    client_id: str
    scope: str

class _TimeoutSettings(SubmodelBase):
    min_fast_request_ms: int
    max_fast_requests: int
    min_slow_request_ms: int

class AppSettings(SettingsBase):

    app_version: str = Field("0.1.0", frozen=True)

    schedule: str = "*/15 * * * *"

    dw_oauth: _OAuthSettings = _OAuthSettings(
        issuer="https://authorize.dailywire.com",
        audience="https://api.dailywire.com/",
        client_id="FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE",
        scope="openid profile offline_access",
    )

    dw_timeout: _TimeoutSettings = _TimeoutSettings(
        min_fast_request_ms=500,            # 0,5 seconds
        max_fast_requests=25,
        min_slow_request_ms=3840000,        # 8 minutes
    )

    database_url: str = "sqlite:///./default.db"
    log_level: str = "INFO"

    admin_password_hash: Union[str, Literal[False]] = False

    # Ephemeral input (never dumped, never repr) – only used to get WL_ADMIN_PASS
    admin_pass: Optional[str] = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    @field_validator("admin_pass", mode="before")
    @classmethod
    def _normalize_password(cls, v: Optional[str]):
        if v is None:
            return None
        if isinstance(v, str) and (v.strip().lower() == "false" or v.strip() == "0" or v.strip() == ""):
            return None
        return v

    @model_validator(mode="after")
    def _finalize_password(self):
        if self.admin_pass:
            self.admin_password_hash = hash_password_scrypt(self.admin_pass)
            os.environ["WL_ADMIN_PASS_HASH"] = str(self.admin_password_hash)
        elif self._normalize_password(os.environ.get("WL_ADMIN_PASS_HASH")):
            self.admin_password_hash = os.environ["WL_ADMIN_PASS_HASH"]
        else:
            self.admin_password_hash = False

        # scrub plaintext + env
        object.__setattr__(self, "admin_pass", None)
        os.environ.pop("WL_ADMIN_PASS", None)

        return self

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
