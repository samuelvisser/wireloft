from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import create_database_fields, update_database_fields
from backend.api.models.local_media_profile import LocalMediaProfileAPIUpdate
from backend.api.models.show import ShowAPIRead
from backend.api.models.show_as_bundle import ShowAPICreateBundle
from backend.db.models import Show, LocalMediaProfile, Season
from backend.db.models.download_profile import PodcastDownloadProfile, SeriesDownloadProfile


def upsert_local_media_profile(s: Session, mp_input: dict) -> LocalMediaProfile:

    # Upsert media profile
    if mp_input['op'] == "create_new":
        local_media_profile = create_database_fields(LocalMediaProfile, mp_input)
        s.add(local_media_profile)
        return local_media_profile
    elif mp_input['op'] == "update_by_slug":
        mp_api = LocalMediaProfileAPIUpdate.model_validate(mp_input)
        data = mp_api.model_dump(exclude_none=True, exclude_unset=True)

        slug = data.get("slug")
        if not slug:
            raise ValueError("update_by_slug requires a slug")

        local_media_profile: Optional[LocalMediaProfile] = (
            s.query(LocalMediaProfile)
            .filter_by(slug=slug)
            .one_or_none()
        )
        if local_media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        update_database_fields(local_media_profile, mp_api)
        return local_media_profile
    else:
        # Fallback, though discriminator should prevent this
        raise ValueError("Unsupported media profile operation")


def create_show_bundle(s: Session, payload: ShowAPICreateBundle) -> ShowAPIRead:

    # Create show
    show = create_database_fields(Show, payload.show.model_dump(exclude_none=True))
    s.add(show)

    # Create seasons
    seasons: list[Season] = []
    index = 1
    for season_in in payload.seasons:
        season = create_database_fields(Season, season_in.model_dump(exclude_none=True))
        season.index = index
        index += 1
        season.show = show      # Set relationship
        s.add(season)
        seasons.append(season)

    # Upsert media profile
    local_media_profile = upsert_local_media_profile(s, payload.local_media_profile.model_dump(exclude_none=True, exclude_unset=True))

    # Create either podcast or series download profile
    if payload.download_profile.op == "podcast":
        download_profile = create_database_fields(PodcastDownloadProfile, payload.download_profile.model_dump(exclude_none=True, exclude_unset=True))
    elif payload.download_profile.op == "series":
        download_profile = create_database_fields(SeriesDownloadProfile, payload.download_profile.model_dump(exclude_none=True, exclude_unset=True, exclude={"seasons"}))

        series_profile_seasons: set[Season] = set()
        for season in seasons:
            for season_in_profile in payload.download_profile.seasons:
                if season.slug == season_in_profile.slug:
                    series_profile_seasons.add(season)
                    break

        download_profile.seasons = list(series_profile_seasons)
    else:
        raise ValueError("Unsupported download profile operation")
    s.add(download_profile)
    download_profile.show = show
    download_profile.local_media_profile = local_media_profile

    s.flush()
    return ShowAPIRead.model_validate(show)