from __future__ import annotations

from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase
from backend.utils.episode_download_scope import EpisodeDownloadScope
from task_manager.events.transactional import queue_event


DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT = "download_profile.run_requested"
DownloadProfileRunResourceType = Literal["download_profile", "show", "episode"]
_DOWNLOAD_PROFILE_RUN_RESOURCE_TYPES = frozenset({"download_profile", "show", "episode"})


def request_download_profile_run(
        s: Session,
        *,
        resource_type: DownloadProfileRunResourceType,
        resource_id: int,
) -> None:
    """Queue one explicitly scoped Download Profile worker run after commit."""
    if resource_type not in _DOWNLOAD_PROFILE_RUN_RESOURCE_TYPES:
        raise ValueError(f"Unsupported Download Profile run resource type: {resource_type}")
    if resource_id <= 0:
        raise ValueError("A scoped Download Profile run requires a positive resource id")

    queue_event(s, DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT, {
        "resource_type": resource_type,
        "resource_id": resource_id,
    })


def _lock_download_profile(s: Session, profile_id: int) -> DownloadProfileBase | None:
    """Load one Download Profile while serializing changes to its enabled state.

    PostgreSQL can lock the profile row directly. SQLite ignores ``FOR UPDATE``,
    so use a no-op SQL update there to acquire its write lock before reading the
    current value. Raw SQL deliberately avoids the model's ``updated_at`` onupdate.
    """
    statement = select(DownloadProfileBase).where(DownloadProfileBase.id == profile_id)
    if s.get_bind().dialect.name == "sqlite":
        s.execute(
            text("UPDATE download_profiles SET id = id WHERE id = :profile_id"),
            {"profile_id": profile_id},
        )
    else:
        statement = statement.with_for_update()

    return s.scalars(
        statement.execution_options(populate_existing=True)
    ).one_or_none()


def lock_enabled_download_profile(
        s: Session,
        profile_id: int,
) -> DownloadProfileBase | None:
    """Lock and return a Download Profile only when it is currently enabled."""
    profile = _lock_download_profile(s, profile_id)
    if profile is None or not profile.enable_profile:
        return None
    return profile


def disable_download_profiles_for_episode_scope(
        s: Session,
        scope: EpisodeDownloadScope,
) -> int:
    """Disable enabled Download Profiles whose Local Media Profile is in ``scope``.

    The caller owns the transaction. Holding the same profile lock used by the
    Download Profile worker makes disabling and automatic reconciliation mutually
    exclusive: either an in-flight reconciliation commits first and can then be
    canceled, or the disable commits first and the worker observes it as disabled.
    """
    local_media_profile_ids = scope.local_media_profile_ids
    if not local_media_profile_ids:
        return 0

    statement = select(DownloadProfileBase).where(
        DownloadProfileBase.show_id == scope.show.id,
        DownloadProfileBase.local_media_profile_id.in_(local_media_profile_ids),
    )
    if s.get_bind().dialect.name == "sqlite":
        # SQLite has a database-wide writer lock. Acquire it before selecting the
        # profiles so the enabled-state read cannot race a profile reconciliation.
        s.execute(
            text("UPDATE download_profiles SET id = id WHERE show_id = :show_id"),
            {"show_id": scope.show.id},
        )
    else:
        statement = statement.with_for_update()

    profiles = list(s.scalars(
        statement.execution_options(populate_existing=True)
    ))
    disabled = 0
    for profile in profiles:
        if not profile.enable_profile:
            continue
        profile.enable_profile = False
        disabled += 1
        queue_event(s, "download_profile.updated", {
            "resource_id": profile.id,
            "id": profile.id,
            "show_id": profile.show_id,
            "profile_type": profile.type,
        })
        request_download_profile_run(
            s,
            resource_type="download_profile",
            resource_id=profile.id,
        )

    s.flush()
    return disabled
