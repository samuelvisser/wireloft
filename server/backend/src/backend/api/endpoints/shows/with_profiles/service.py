from __future__ import annotations

from sqlalchemy.orm import Session

from backend.api.endpoints.podcast_download_profiles.service import create_download_profile_podcast
from backend.api.endpoints.series_download_profiles.service import create_download_profile_series
from backend.api.endpoints.media_profiles.service import create_media_profile, update_media_profile
from backend.api.endpoints.shows.service import create_show
from backend.api.models.show import ShowAPIRead
from backend.api.models.show_with_profiles import ShowAPICreateBundle
from backend.api.models.download_profile_podcast import DownloadProfilePodcastAPICreate
from backend.api.models.download_profile_series import DownloadProfileSeriesAPICreate


def create_show_bundle(s: Session, payload: ShowAPICreateBundle) -> ShowAPIRead:
    # Create the show first
    show_read = create_show(s, payload.show)  # should raise 409 on slug conflict

    # Upsert media profile and get its ID
    mp_input = payload.media_profile
    if mp_input.op == "create_new":
        mp_read = create_media_profile(s, mp_input)
    elif mp_input.op == "update_by_slug":
        mp_read = update_media_profile(s, mp_input.slug, mp_input)
    else:
        # Fallback, though discriminator should prevent this
        raise ValueError("Unsupported media profile operation")

    media_profile_id = mp_read.id

    # Create the appropriate download profile, adding foreign keys
    dp = payload.download_profile
    if dp.op == "podcast":
        dp_create = DownloadProfilePodcastAPICreate(
            show_id=show_read.id,
            media_profile_id=media_profile_id,
            enable_profile=dp.enable_profile,
            download_with_countdown=dp.download_with_countdown,
            redownload_final=dp.redownload_final,
            download_days_in_past=dp.download_days_in_past,
            delete_older_episodes=dp.delete_older_episodes,
        )
        create_download_profile_podcast(s, dp_create)

    elif dp.op == "series":
        dp_create = DownloadProfileSeriesAPICreate(
            show_id=show_read.id,
            media_profile_id=media_profile_id,
            enable_profile=dp.enable_profile,
            include_upcoming_seasons=dp.include_upcoming_seasons,
        )
        create_download_profile_series(s, dp_create)
        # Optional: season list can be handled later (associations)

    else:
        raise ValueError("Unsupported download profile op")

    return show_read
