from wireloft_config.security.passwords import hash_password_scrypt, derive_admin_password_client_value
from wireloft_config.settings.base import SubmodelBase

from typing import Optional
from pydantic import Field, field_validator, model_validator

import os


class OAuthSettings(SubmodelBase):
    issuer: str = Field(default="https://authorize.dailywire.com", description="Issuer URL for OAuth authentication")
    audience: str = Field(default="https://api.dailywire.com/", description="Audience URL for OAuth authentication")
    client_id: str = Field(default="FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE", description="Client ID for OAuth authentication")
    scope: str = Field(default="openid profile offline_access", description="Scope for OAuth authentication")


class TimeoutSettings(SubmodelBase):
    min_fast_request_ms: int = Field(default=500, description="Minimum time in milliseconds for a fast request")
    max_fast_requests: int = Field(default=25, description="Maximum number of fast requests allowed")
    min_slow_request_ms: int = Field(default=3840000, description="Milliseconds to wait after max fast requests where made")


class SessionSettings(SubmodelBase):
    ttl_seconds: int = Field(default=60 * 60 * 24 * 30, description="Time in seconds the session stays valid")    # 30 days default session lifetime


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
