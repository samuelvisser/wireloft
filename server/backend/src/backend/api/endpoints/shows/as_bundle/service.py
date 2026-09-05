from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException, Request

from backend.api.helpers import create_database_fields, update_database_fields
from backend.api.models.local_media_profile import LocalMediaProfileAPIUpdate
from backend.api.models.show import ShowAPIRead
from backend.api.models.show_as_bundle import ShowAPICreateBundle
from backend.db.models import LocalMediaProfileBase, Season, Show, ShowLocalMediaProfile
from backend.db.models.download_profile import PodcastDownloadProfile, SeriesDownloadProfile
from backend.db.models.stream_profile import RssStreamProfile
from backend.utils.feed_urls import build_rss_feed_url
from backend.utils.helpers import generate_stream_profile_token
from backend.utils.season_ordering import order_initial_seasons
from task_manager.scheduler.operation_factory import OperationFactory

from ..operations import ShowIndexOperation


def upsert_local_media_profile(s: Session, mp_input: dict) -> LocalMediaProfileBase:
    if mp_input['op'] == "create_new":
        local_media_profile = create_database_fields(ShowLocalMediaProfile, mp_input)
        s.add(local_media_profile)
        return local_media_profile
    elif mp_input['op'] == "update_by_slug":
        mp_api = LocalMediaProfileAPIUpdate.model_validate(mp_input)
        data = mp_api.model_dump(exclude_none=True, exclude_unset=True)

        slug = data.get("slug")
        if not slug:
            raise ValueError("update_by_slug requires a slug")

        local_media_profile: Optional[ShowLocalMediaProfile] = (
            s.query(ShowLocalMediaProfile)
            .filter_by(slug=slug)
            .one_or_none()
        )
        if local_media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        update_database_fields(local_media_profile, mp_api)
        return local_media_profile
    else:
        raise ValueError("Unsupported media profile operation")


def create_show_bundle(s: Session, request: Request, payload: ShowAPICreateBundle) -> ShowAPIRead:
    show = create_database_fields(Show, payload.show.model_dump(exclude_none=True))
    s.add(show)

    # The Add Show flow supplies seasons as part of the initial bundle, before the
    # fetch-new-episodes worker runs. Normalize them here so their persistent
    # indices are correct from the moment they are first stored.
    seasons: list[Season] = []
    for index, season_in in enumerate(order_initial_seasons(payload.seasons), start=1):
        season = create_database_fields(Season, season_in.model_dump(exclude_none=True))
        season.index = index
        season.show = show
        s.add(season)
        seasons.append(season)

    local_media_profile: Optional[LocalMediaProfileBase] = None
    if payload.local_media_profile is not None:
        local_media_profile = upsert_local_media_profile(
            s,
            payload.local_media_profile.model_dump(exclude_none=True, exclude_unset=True),
        )

    if payload.download_profile is not None:
        if local_media_profile is None:
            raise ValueError("A local media profile is required when creating a download profile")

        if payload.download_profile.op == "podcast":
            download_profile = create_database_fields(
                PodcastDownloadProfile,
                payload.download_profile.model_dump(exclude_none=True, exclude_unset=True),
            )
        elif payload.download_profile.op == "series":
            download_profile = create_database_fields(
                SeriesDownloadProfile,
                payload.download_profile.model_dump(exclude_none=True, exclude_unset=True, exclude={"seasons"}),
            )

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

    if payload.stream_profile is not None:
        stream_data = payload.stream_profile.model_dump(by_alias=True, exclude_none=True)
        stream_data.pop("show_id", None)
        feed_url = (stream_data.pop("feed_url", None) or "").strip()
        token = generate_stream_profile_token()
        stream_profile = RssStreamProfile(
            **stream_data,
            token=token,
            feed_url=feed_url or build_rss_feed_url(request, token=token, show_slug=show.slug),
        )
        stream_profile.show = show
        s.add(stream_profile)

    s.flush()
    OperationFactory.create(s, ShowIndexOperation(show))
    return ShowAPIRead.model_validate(show)
