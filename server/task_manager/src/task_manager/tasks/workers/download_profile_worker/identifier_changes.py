from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.utils.output_template import output_template_fields
from task_manager.scheduler.executor import trigger_now
from ._helpers import get_download_profile_episodes, resolve_target_profiles


logger = logging.getLogger(__name__)
_IDENTIFIER_PATH_FIELDS = frozenset({"episode_identifier", "episode_label"})
_REDOWNLOAD_TASK_KEY = "redownload_show_episodes_worker"


def handle_episode_identifier_changed(
        s: Session,
        *,
        episode_id: int | None,
        old_episode_identifier: str,
        new_episode_identifier: str,
) -> int:
    """Queue targeted re-downloads for identifier-sensitive Download Profiles.

    A Download Profile is affected only when it still includes this exact episode
    under its current rules and its Local Media Profile actually references one of
    the identifier-derived path variables. Profiles sharing one Local Media Profile
    are de-duplicated because they point at the same persistent artifact/path.
    """
    if episode_id is None:
        return 0

    episode = s.get(Episode, episode_id)
    if episode is None:
        logger.info(
            "Skipping identifier-change download handling for deleted episode %s",
            episode_id,
        )
        return 0

    profile_ids_by_local_media_profile: dict[int, int] = {}
    profiles = resolve_target_profiles(
        s,
        resource_type="episode",
        resource_id=episode.id,
    )
    for profile in sorted(profiles, key=lambda item: item.id):
        if not get_download_profile_episodes(s, profile, only_episode=episode):
            continue

        local_media_profile = profile.local_media_profile
        if local_media_profile is None:
            continue
        try:
            fields = output_template_fields(local_media_profile.output_template)
        except ValueError:
            logger.warning(
                "Could not inspect Local Media Profile %s after episode identifier change",
                local_media_profile.id,
                exc_info=True,
            )
            continue
        if not (fields & _IDENTIFIER_PATH_FIELDS):
            continue

        profile_ids_by_local_media_profile.setdefault(
            profile.local_media_profile_id,
            profile.id,
        )

    profile_ids = list(profile_ids_by_local_media_profile.values())
    if not profile_ids:
        logger.info(
            "Episode %s identifier changed %s -> %s; no eligible identifier-sensitive Download Profiles",
            episode.id,
            old_episode_identifier,
            new_episode_identifier,
        )
        return 0

    # End this event worker's read transaction before the newly scheduled workers
    # open independent sessions and potentially cancel/replace active downloads.
    s.rollback()
    for profile_id in profile_ids:
        trigger_now(
            def_key=_REDOWNLOAD_TASK_KEY,
            resource_type="episode",
            resource_id=episode_id,
            max_retries=0,
            download_profile_id=profile_id,
        )

    logger.info(
        "Episode %s identifier changed %s -> %s; queued %s targeted re-download(s)",
        episode_id,
        old_episode_identifier,
        new_episode_identifier,
        len(profile_ids),
    )
    return len(profile_ids)
