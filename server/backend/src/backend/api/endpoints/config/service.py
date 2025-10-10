from __future__ import annotations

from wireloft_config import get_settings

from backend.api.models.config_public import *


def get_public_config() -> ConfigPublicRead:
    s = get_settings()

    print(s.model_dump_json())

    config = ConfigPublicRead(
        app_version=s.app_version,
        session=PublicSessionConfig(**s.session.model_dump(exclude_none=True)),
        admin_auth=PublicAdminAuth(**s.admin_auth.model_dump(exclude_none=True)),
    )

    print(config.model_dump_json())

    return config