from __future__ import annotations

from wireloft_config import get_settings

from backend.api.models.config_public import *


def get_public_config() -> ConfigPublicRead:
    s = get_settings()

    ## We assign values very explicitly to prevent ever exposing app secrets to the public API
    config = ConfigPublicRead(
        app_version=s.app_version,
        login_session=PublicSessionConfig(
            ttl_seconds=s.login_session.ttl_seconds
        ),
        admin_auth=PublicAdminAuth(
            enabled=s.admin_auth.enabled
        ),
    )

    return config