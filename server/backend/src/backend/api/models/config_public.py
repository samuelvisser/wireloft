from __future__ import annotations

from pydantic import Field, ConfigDict

from backend.api.models.base import ResponseBase


class _PublicConfigBaseOut(ResponseBase):
    """Base class for public config models.
    Makes sure that extra fields are ignored.
    Currently, the parent also sets them to ignore. But because not exposing secrets is very important,
    we overwrite it here to make sure extra fields always stay ignored, even if the parent setting changes.
    """

    # Force ignoring of extra fields while preserving all other parent model_config values
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        base_cfg = getattr(cls, "model_config", {}) or {}
        cls.model_config = ConfigDict(**{**base_cfg, "extra": "ignore"})

        # Rebuild schema if available
        rebuild = getattr(cls, "model_rebuild", None)
        if callable(rebuild):
            rebuild(force=True, raise_errors=False)
        else:
            # If rebuild isn't available yet, defer to Pydantic's first-use build
            pass


class PublicSessionConfig(_PublicConfigBaseOut):
    ttl_seconds: int


class PublicAdminAuth(_PublicConfigBaseOut):
    enabled: bool = Field(description="Whether admin auth is enabled (derived from presence of a configured password hash)")


class ConfigPublicRead(_PublicConfigBaseOut):
    app_version: str
    session: PublicSessionConfig
    admin_auth: PublicAdminAuth
