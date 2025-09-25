from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import create_database_fields, update_database_fields
from backend.api.models.media_profile import MediaProfileAPIUpdate
from backend.api.models.show import ShowAPIRead
from backend.api.models.show_with_profiles import ShowAPICreateBundle
from backend.db.models import Show, MediaProfile, Season, DownloadProfileSeries, DownloadProfilePodcast


def upsert_media_profile(s: Session, mp_input: dict) -> MediaProfile:

    # Upsert media profile
    if mp_input['op'] == "create_new":
        media_profile = create_database_fields(MediaProfile, mp_input)
        s.add(media_profile)
        return media_profile
    elif mp_input['op'] == "update_by_slug":
        mp_api = MediaProfileAPIUpdate.model_validate(mp_input)
        data = mp_api.model_dump(exclude_none=True, exclude_unset=True)

        slug = data.get("slug")
        if not slug:
            raise ValueError("update_by_slug requires a slug")

        media_profile = (
            s.query(MediaProfile)
            .filter_by(slug=slug)
            .one_or_none()
        )
        if media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        update_database_fields(media_profile, mp_api)
        return media_profile
    else:
        # Fallback, though discriminator should prevent this
        raise ValueError("Unsupported media profile operation")


def create_show_bundle(s: Session, payload: ShowAPICreateBundle) -> ShowAPIRead:

    # Create show
    show = create_database_fields(Show, payload.show.model_dump(exclude_none=True))
    s.add(show)

    # Create seasons
    seasons: list[Season] = []
    for season_in in payload.seasons:
        season = create_database_fields(Season, season_in.model_dump(exclude_none=True))
        season.show = show      # Set relationship
        s.add(season)
        seasons.append(season)

    # Upsert media profile
    media_profile = upsert_media_profile(s, payload.media_profile.model_dump(exclude_none=True, exclude_unset=True))

    # Create either podcast or series download profile
    if payload.download_profile.op == "podcast":
        download_profile = create_database_fields(DownloadProfilePodcast, payload.download_profile.model_dump(exclude_none=True, exclude_unset=True))
    elif payload.download_profile.op == "series":
        download_profile = create_database_fields(DownloadProfileSeries, payload.download_profile.model_dump(exclude_none=True, exclude_unset=True, exclude={"seasons"}))

        series_profile_seasons: set[Season] = set()
        for season in seasons:
            for season_in_profile in payload.download_profile.seasons:
                if season.dw_id == season_in_profile.dw_id or season.slug == season_in_profile.slug:
                    series_profile_seasons.add(season)
                    break

        download_profile.seasons = list(series_profile_seasons)
    else:
        raise ValueError("Unsupported download profile operation")
    s.add(download_profile)
    download_profile.show = show
    download_profile.media_profile = media_profile

    s.flush()
    return ShowAPIRead.model_validate(show)