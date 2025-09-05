from __future__ import annotations
import datetime as dt
import random
from typing import List, Dict, Any


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def random_datetime(start: dt.datetime | None = None, end: dt.datetime | None = None) -> dt.datetime:
    if start is None:
        start = dt.datetime(2016, 1, 1, tzinfo=dt.timezone.utc)
    if end is None:
        end = dt.datetime(2025, 9, 1, tzinfo=dt.timezone.utc)
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    if start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    random_ts = random.uniform(start_ts, end_ts)
    return dt.datetime.fromtimestamp(random_ts, tz=dt.timezone.utc)


def _status_for(start: int, index: int) -> str:
    _status_cycle = ["downloaded", "downloading", "processing", "error"]
    return _status_cycle[(start + (index - 1)) % len(_status_cycle)]


def _slugify(text: str | None) -> str:
    if not text:
        return ""
    s = str(text).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        elif ch.isspace() or ch in "/\\":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


# Hardcoded media profiles
media_profiles: List[Dict[str, Any]] = [
    {
        "id": 1,
        "slug": "default-1080p",
        "name": "Default 1080p",
        "output_template": "D:/Media/Shows/{show}/{season}",
        "preferred_format": "1080p",
        "download_series_images": True,
        "created_date": _now(),
        "modified_date": _now(),
    },
    {
        "id": 2,
        "slug": "mobile-720p",
        "name": "Mobile 720p backend",
        "output_template": "E:/Mobile/Shows/{show}",
        "preferred_format": "720p",
        "download_series_images": False,
        "created_date": _now(),
        "modified_date": _now(),
    },
]


# Hardcoded shows (no embedded episodes)
shows: List[Dict[str, Any]] = [
    {
        "id": 1,
        "uuid": "uuid-1",
        "dw_id": "dw-1",
        "slug": "the-ben-shapiro-show",
        "media_profile_id": 1,
        "title": "The Ben Shapiro Show",
        "description": None,
        "url": "https://www.dailywire.com/show/the-ben-shapiro-show",
        "status": "active",
        "media_type": "show",
        "author_name": "Ben Shapiro",
        "author_slug": _slugify("Ben Shapiro"),
        "author_headshot_path": None,
        "download_media": True,
        "download_delay_minutes": 0,
        "redownload_delay_minutes": 0,
        "download_days_in_past": 0,
        "delete_older_episodes": True,
        "title_filter": None,
        "background_image_path": None,
        "logo_image_path": None,
        "thumbnail_landscape_path": None,
        "thumbnail_portrait_path": None,
        "thumbnail_square_path": None,
        "created_date": _now(),
        "modified_date": _now(),
    },
    {
        "id": 2,
        "uuid": "uuid-2",
        "dw_id": "dw-2",
        "slug": "the-matt-walsh-show",
        "media_profile_id": 1,
        "title": "The Matt Walsh Show",
        "description": None,
        "url": "https://www.dailywire.com/show/the-matt-walsh-show",
        "status": "active",
        "media_type": "show",
        "author_name": "Matt Walsh",
        "author_slug": _slugify("Matt Walsh"),
        "author_headshot_path": None,
        "download_media": True,
        "download_delay_minutes": 0,
        "redownload_delay_minutes": 0,
        "download_days_in_past": 0,
        "delete_older_episodes": True,
        "title_filter": None,
        "background_image_path": None,
        "logo_image_path": None,
        "thumbnail_landscape_path": None,
        "thumbnail_portrait_path": None,
        "thumbnail_square_path": None,
        "created_date": _now(),
        "modified_date": _now(),
    },
    {
        "id": 3,
        "uuid": "uuid-3",
        "dw_id": "dw-3",
        "slug": "ben-after-dark",
        "media_profile_id": 2,
        "title": "Ben After Dark",
        "description": None,
        "url": "https://www.dailywire.com/show/ben-after-dark",
        "status": "active",
        "media_type": "show",
        "author_name": "Ben Shapiro",
        "author_slug": _slugify("Ben Shapiro"),
        "author_headshot_path": None,
        "download_media": True,
        "download_delay_minutes": 0,
        "redownload_delay_minutes": 0,
        "download_days_in_past": 0,
        "delete_older_episodes": True,
        "title_filter": None,
        "background_image_path": None,
        "logo_image_path": None,
        "thumbnail_landscape_path": None,
        "thumbnail_portrait_path": None,
        "thumbnail_square_path": None,
        "created_date": _now(),
        "modified_date": _now(),
    },
]


# Hardcoded episodes (flat), each references a show via show_id (the show id)
episodes: List[Dict[str, Any]] = []

# The Ben Shapiro Show: 30 episodes, starting with "downloaded"
for i in range(1, 31):
    episodes.append({
        "id": i,
        "index": i,
        "show_id": 1,
        "uuid": f"uuid-1-{i}",
        "dw_id": f"dw-1-{i}",
        "slug": f"the-ben-shapiro-show-{i}",
        "title": f"The Ben Shapiro Show — Episode {i}",
        "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "status": _status_for(0, i),
        "went_live_date": random_datetime(),
        "published_date": random_datetime(),
        "downloaded_date": random_datetime(),
        "redownloaded_date": random_datetime(),
        "created_date": random_datetime(),
        "modified_date": random_datetime(),
    })

# The Matt Walsh Show: 20 episodes, starting with "processing"
for i in range(1, 21):
    episodes.append({
        "id": i,
        "index": i,
        "show_id": 2,
        "uuid": f"uuid-2-{i}",
        "dw_id": f"dw-2-{i}",
        "slug": f"the-matt-walsh-show-{i}",
        "title": f"The Matt Walsh Show — Episode {i}",
        "description": "Consectetur adipiscing elit.",
        "status": _status_for(2, i),
        "went_live_date": random_datetime(),
        "published_date": random_datetime(),
        "downloaded_date": random_datetime(),
        "redownloaded_date": random_datetime(),
        "created_date": random_datetime(),
        "modified_date": random_datetime(),
    })

# Ben After Dark: 7 episodes, starting with "processing"
for i in range(1, 8):
    episodes.append({
        "id": i,
        "index": i,
        "show_id": 3,
        "uuid": f"uuid-3-{i}",
        "dw_id": f"dw-3-{i}",
        "slug": f"ben-after-dark-{i}",
        "title": f"Ben After Dark — Episode {i}",
        "description": None,
        "status": _status_for(2, i),
        "went_live_date": random_datetime(),
        "published_date": random_datetime(),
        "downloaded_date": random_datetime(),
        "redownloaded_date": random_datetime(),
        "created_date": random_datetime(),
        "modified_date": random_datetime(),
    })

# Hardcoded settings
settings: List[Dict[str, Any]] = [
    {
        "id": 1,
        "slug": "download_root",
        "name": "Download root path",
        "value": "D:\\Downloads\\DailyWire",
        "created_date": _now(),
        "modified_date": _now(),
    },
    {
        "id": 2,
        "slug": "concurrency",
        "name": "Concurrent downloads",
        "value": "2",
        "created_date": _now(),
        "modified_date": _now(),
    },
]
