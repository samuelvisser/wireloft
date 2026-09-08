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
    """Queue targeted re-downloads for identifier-sensitive Local Media Profiles.

    Download Profiles still determine whether an identifier change should cause an
    automatic replacement. Once selected, the replacement itself targets the
    persistent artifact by Local Media Profile, so manually created media rows and
    Download Profile provenance are never rewritten by the re-download worker.
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

    local_media_profile_ids: set[int] = set()
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

        local_media_profile_ids.add(profile.local_media_profile_id)

    if not local_media_profile_ids:
        logger.info(
            "Episode %s identifier changed %s -> %s; no eligible identifier-sensitive Local Media Profiles",
            episode.id,
            old_episode_identifier,
            new_episode_identifier,
        )
        return 0

    # End this event worker's read transaction before the newly scheduled workers
    # open independent sessions and potentially cancel/replace active downloads.
    s.rollback()
    for local_media_profile_id in sorted(local_media_profile_ids):
        trigger_now(
            def_key=_REDOWNLOAD_TASK_KEY,
            resource_type="episode",
            resource_id=episode_id,
            max_retries=0,
            local_media_profile_id=local_media_profile_id,
        )

    logger.info(
        "Episode %s identifier changed %s -> %s; queued %s targeted re-download(s)",
        episode_id,
        old_episode_identifier,
        new_episode_identifier,
        len(local_media_profile_ids),
    )
    return len(local_media_profile_ids)
