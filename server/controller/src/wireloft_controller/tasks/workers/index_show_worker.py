from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any

from backend.db.core import get_session
from backend.db.models import Show
from backend.db.models.media_item import Episode
from backend.db.models import Season
from backend.utils.helpers import generate_uuid

from dailywire_api.dw_api.client import (
    MiddlewareClient,
    ByShowSeason,
    ByPodcastSeason,
)
from dailywire_api.records import EpisodeRecord
from dailywire_authorisation import DeviceAuthClient

from ...registry import task


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


@task(
    key="index_show_worker",
    title="Index show episodes",
    description="Fetch all episodes for a show from DailyWire and store them with ascending indices (oldest→newest).",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def index_show_worker(*, resource_id: int, progress):
    """Index a show's episodes into the local database if none exist yet.

    - If the show already has any episodes stored, the task exits.
    - Otherwise, it fetches all seasons and all episodes from DailyWire,
      sorts episodes from oldest to newest, and inserts them with index 1..N.

    Any exception will be propagated so the scheduler can schedule a retry.
    """
    s = get_session()
    try:
        show = s.get(Show, resource_id)
        if show is None:
            raise ValueError(f"Show id={resource_id} not found")

        # If any episode already exists for this show, do nothing
        existing_any = s.query(Episode).filter(Episode.show_id == show.id).first()
        if existing_any is not None:
            return

        # Prepare API client with access token if available
        tokens = None
        try:
            tokens = DeviceAuthClient().get_token()
        except Exception:
            tokens = None
        access_token: Optional[str] = getattr(tokens, "access_token", None) if tokens else None
        client = MiddlewareClient(access_token=access_token)

        # Get seasons for this show
        model = client.get_show_page(show.slug)
        sp = model.model_dump(by_alias=True, mode="json")

        seasons_data: List[Dict[str, Any]] = list(sp.get("seasons") or [])

        # Map or create Season rows in DB for this show
        dwid_to_season_dbid: dict[str, int] = {}
        for sd in seasons_data:
            dw_sid = str(sd.get("id"))
            if not dw_sid:
                continue
            slug = str(sd.get("slug") or "").strip() or f"{show.slug}-{dw_sid}"
            name = str(sd.get("name") or slug)
            # Try find by dw_id first
            season_row = s.query(Season).filter(Season.dw_id == dw_sid).one_or_none()
            if season_row is None:
                season_row = Season(dw_id=dw_sid, slug=slug, name=name, show_id=show.id)
                s.add(season_row)
                s.flush()  # get DB id
            dwid_to_season_dbid[dw_sid] = int(season_row.id)

        # Collect all episodes across all seasons
        is_podcast = isinstance(show.type, str) and ("podcast" in show.type.lower())
        collected: List[Tuple[Dict[str, Any], int]] = []  # (episode_dict, season_db_id)

        # Progress bookkeeping
        total_seasons = max(1, len(dwid_to_season_dbid))
        done_seasons = 0

        for dw_sid, season_db_id in dwid_to_season_dbid.items():
            # Page through episodes for this season
            page = 1
            has_more = True
            while has_more:
                selector = (
                    ByPodcastSeason(season_id=dw_sid, page_size=50, page_number=page)
                    if is_podcast else
                    ByShowSeason(season_id=dw_sid, page_size=50, page_number=page)
                )
                res = client.get_episodes_paginated(show.slug, selector)

                item_models = list(res.items or [])
                items = [ep.model_dump(by_alias=True, mode='json') for ep in item_models]

                if not items:
                    has_more = False
                    break
                for ep in items:
                    collected.append((ep, season_db_id))
                page += 1
                has_more = res.has_next

            done_seasons += 1
            progress.set(int(100 * done_seasons / total_seasons), f"Fetched season {done_seasons}/{total_seasons}")

        # Sort oldest -> newest by published_at then scheduled_at
        def _sort_key(t: Tuple[Dict[str, Any], int]):
            ep = t[0]
            p = _parse_dt(ep.get("published_at"))
            if p is None:
                p = _parse_dt(ep.get("scheduled_at"))
            # Fallback to epoch start to keep deterministic ordering
            return p or datetime(1970, 1, 1, tzinfo=timezone.utc)

        collected.sort(key=_sort_key)

        # Insert with ascending index
        for idx, (ep, season_db_id) in enumerate(collected, start=1):
            duration_val = ep.get("duration")
            try:
                duration_int = int(round(float(duration_val))) if duration_val is not None else 0
            except Exception:
                duration_int = 0

            e = Episode(
                uuid=generate_uuid(),
                dw_id=str(ep.get("id")) if ep.get("id") is not None else None,
                slug=str(ep.get("slug")),
                title=str(ep.get("title")),
                description=ep.get("description"),
                duration=duration_int,
                show_id=show.id,
                season_id=season_db_id,
                index=idx,
                publish_status=str(ep.get("status")) if ep.get("status") is not None else "",
                went_live_date=_parse_dt(ep.get("scheduled_at")),
                published_date=_parse_dt(ep.get("published_at")),
                redownloaded_date=None,
            )
            s.add(e)

        s.commit()
        progress.set(100, f"Indexed {len(collected)} episodes for show '{show.slug}'")

    except Exception:
        s.rollback()
        # Propagate so the scheduler can handle retry policy (will schedule retry, typically within ~1 minute)
        raise
    finally:
        s.close()
