from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException, Request

from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.api.models.show import ShowAPIRead
from backend.api.models.show_as_bundle import (
    LocalMediaProfileAPIUpsert,
    LocalMediaProfileCreateNew,
    LocalMediaProfileUpdateBySlug,
    PodcastDownloadProfileCreateInBundle,
    SeriesDownloadProfileCreateInBundle,
    ShowAPICreateBundle,
)
from backend.db.models import LocalMediaProfileBase, Season, Show, ShowLocalMediaProfile
from backend.db.models.download_profile import PodcastDownloadProfile, SeriesDownloadProfile
from backend.db.models.stream_profile import RssStreamProfile
from backend.utils.feed_urls import build_rss_feed_url
from backend.utils.helpers import generate_stream_profile_token
from backend.types.season_types import SeasonType
from backend.utils.season_ordering import order_initial_seasons, season_type_from_name
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operation_factory import create_operation

from ..events import ShowAdded
from ..operations import ShowIndexOperation


def upsert_local_media_profile(
    s: Session,
    mp_input: LocalMediaProfileAPIUpsert,
) -> LocalMediaProfileBase:
    if isinstance(mp_input, LocalMediaProfileCreateNew):
        local_media_profile = create_database_fields(
            ShowLocalMediaProfile,
            mp_input,
            exclude_fields={"op"},
        )
        s.add(local_media_profile)
        return local_media_profile

    if isinstance(mp_input, LocalMediaProfileUpdateBySlug):
        local_media_profile: Optional[ShowLocalMediaProfile] = (
            s.query(ShowLocalMediaProfile)
            .filter_by(slug=mp_input.slug_selector)
            .one_or_none()
        )
        if local_media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        update_database_fields(
            local_media_profile,
            mp_input,
            exclude_fields={"op", "slug_selector"},
        )
        return local_media_profile

    raise TypeError(f"Unsupported media profile input {type(mp_input).__name__}")



def create_show_bundle(s: Session, request: Request, payload: ShowAPICreateBundle) -> ShowAPIRead:
    show = create_database_fields(Show, payload.show)
    s.add(show)

    # The Add Show flow supplies seasons as part of the initial bundle, before the
    # fetch-new-episodes worker runs. Normalize them here so their persistent
    # indices are correct from the moment they are first stored.
    seasons: list[Season] = []
    regular_season_number = 0
    for index, season_in in enumerate(order_initial_seasons(payload.seasons), start=1):
        season = create_database_fields(Season, season_in)
        season_type = season_type_from_name(season_in.name)
        if season_type is SeasonType.NORMAL:
            regular_season_number += 1
            season_number = regular_season_number
        else:
            season_number = 0
        season.index = index
        season.season_type = season_type.value
        season.season_number = season_number
        season.show = show
        s.add(season)
        seasons.append(season)

    local_media_profile: Optional[LocalMediaProfileBase] = None
    if payload.local_media_profile is not None:
        local_media_profile = upsert_local_media_profile(s, payload.local_media_profile)

    if payload.download_profile is not None:
        if local_media_profile is None:
            raise ValueError("A local media profile is required when creating a download profile")

        if isinstance(payload.download_profile, PodcastDownloadProfileCreateInBundle):
            download_profile = create_database_fields(
                PodcastDownloadProfile,
                payload.download_profile,
                exclude_fields={"op"},
            )
        elif isinstance(payload.download_profile, SeriesDownloadProfileCreateInBundle):
            download_profile = create_database_fields(
                SeriesDownloadProfile,
                payload.download_profile,
                exclude_fields={"op", "seasons"},
            )
            selected_slugs = {
                season.slug for season in payload.download_profile.seasons
            }
            download_profile.seasons = [
                season for season in seasons if season.slug in selected_slugs
            ]
        else:
            raise TypeError(
                f"Unsupported download profile input {type(payload.download_profile).__name__}"
            )

        s.add(download_profile)
        download_profile.show = show
        download_profile.local_media_profile = local_media_profile

    if payload.stream_profile is not None:
        token = generate_stream_profile_token()
        feed_url = (payload.stream_profile.feed_url or "").strip()
        stream_profile = create_database_fields(
            RssStreamProfile,
            payload.stream_profile,
            exclude_fields={"show_id", "feed_url"},
        )
        stream_profile.token = token
        stream_profile.feed_url = (
            feed_url
            or build_rss_feed_url(request, token=token, show_slug=show.slug)
        )
        stream_profile.show = show
        s.add(stream_profile)

    s.flush()
    create_operation(s, ShowIndexOperation(show))
    queue_event(s, "show.added", ShowAdded(show))
    return ShowAPIRead.model_validate(show)
