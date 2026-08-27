from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import Show
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason
from dailywire_api.types.user_info import DwMembershipLevel
from controller.m3u8 import get_vod_info
from controller.m3u8.get_vod_info import _fmt_hhmmss
from ...helpers.episodes.status import get_publish_status_from_dw_detail, is_published_final
from ...helpers.shows.get import get_show_from_params


# Registered as a task in entrypoint.py; this service function expects an open session.
async def run_debug_ep_details(s: Session, *, show_slug: str, progress):  # progress provided by executor
    print("Starting debug_ep_details")

    # Get show for the new episode
    show: Show | None = get_show_from_params(s, show_slug=show_slug)
    if show is None:
        raise ValueError("Show not found; provide a valid show_slug")
    else:
        print(f"Found show {show.slug} with id {show.id}")

    # Get the latest season
    if show.seasons is None or len(show.seasons) == 0:
        raise ValueError("Show has no seasons")
    latest_db_season = show.seasons[0]

    # Get latest episode from DW
    client = MiddlewareClient()
    season_dw_id = client.get_season_id_by_slugs(show.slug, latest_db_season.slug)
    latest_dw_episode, _, _ = client.get_episodes_paginated(show.slug, ByShowSeason(
        season_dw_id=season_dw_id,
        membership_plan=show.membership_level,
        page_size=1,
        order_by="CreatedAt_DESC"
    ))
    latest_dw_episode = latest_dw_episode[0] if len(latest_dw_episode) > 0 else None

    if latest_dw_episode is None:
        raise ValueError(f"No DW episodes found for show {show.slug}")
    print(f"Latest dw ep for {show.slug}: {latest_dw_episode.title}")

    # Get details for all retrieved latest episodes
    dw_ep_detail = client.get_episode_details(latest_dw_episode.slug, require_member_exclusive=show.membership_level != DwMembershipLevel.FREE.value)

    print("-----------------------------")
    print(f"DW ep - {dw_ep_detail.title}")
    print(f"DW ep - duration: {dw_ep_detail.duration}")
    print(f"DW ep - publish_status: {dw_ep_detail.publish_status}")
    print(f"DW ep - published_date: {dw_ep_detail.published_date}")
    print(f"DW ep - delivery_mode: {dw_ep_detail.delivery_mode}")
    print(f"DW ep - playback_status: {dw_ep_detail.playback_status}")
    print("-----------------------------")
    print(f"WL - publish_status: {get_publish_status_from_dw_detail(dw_ep_detail)}")
    print(f"WL - is_final: {"True" if is_published_final(dw_ep_detail) else "False" }")
    print("-----------------------------")

    info = get_vod_info(dw_ep_detail.video_url)
    print(f"type={info.playlist_type}")
    print(f"seconds={info.seconds}")
    print(f"hhmmss={_fmt_hhmmss(info.seconds)}")
    print(f"segments={info.segments}")
    print(f"variant_url={info.variant_url}")

    print("-----------------------------")
    print(f"Full dw_ep_detail: {dw_ep_detail.__dict__}")
    print("debug_ep_details completed")

