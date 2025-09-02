from __future__ import annotations
import datetime as dt
import random

# Hardcoded media profiles (moved from React UI / kept for seeding and demo API)
media_profiles = [
    {
        "id": "p1",
        "name": "Default 1080p",
        "outputPathTemplate": "D:/Media/Shows/{show}/{season}",
        "preferredFormat": "1080p",
        "downloadSeriesImages": True,
    },
    {
        "id": "p2",
        "name": "Mobile 720p backend",
        "outputPathTemplate": "E:/Mobile/Shows/{show}",
        "preferredFormat": "720p",
        "downloadSeriesImages": False,
    },
]

# Hardcoded shows (no embedded episodes)
shows = [
    {
        "id": "1",
        "uuid": "uuid-1",
        "dw_id": "dw-1",
        "slug": "the-ben-shapiro-show",
        "url": "https://www.dailywire.com/show/the-ben-shapiro-show",
        "author": "Ben Shapiro",
        "title": "The Ben Shapiro Show",
        "years": "2015-2025",
    },
    {
        "id": "2",
        "uuid": "uuid-2",
        "dw_id": "dw-2",
        "slug": "the-matt-walsh-show",
        "author": "Matt Walsh",
        "title": "The Matt Walsh Show",
        "years": "2018 – 2025",
    },
    {
        "id": "3",
        "uuid": "uuid-3",
        "dw_id": "dw-3",
        "slug": "ben-after-dark",
        "author": "Ben Shapiro",
        "title": "Ben After Dark",
        "years": "2025 - 2025",
    },
]

def random_datetime(start: dt.datetime | None = None, end: dt.datetime | None = None) -> str:
    if start is None:
        start = dt.datetime(2016, 1, 1, tzinfo=dt.timezone.utc)
    if end is None:
        end = dt.datetime(2025, 9, 1, tzinfo=dt.timezone.utc)
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    if start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    random_ts = random.uniform(start_ts, end_ts)
    return dt.datetime.fromtimestamp(random_ts, tz=dt.timezone.utc).isoformat()

def _status_for(start: int, index: int) -> str:
    _status_cycle = ["downloaded", "downloading", "processing", "error"]
    return _status_cycle[(start + (index - 1)) % len(_status_cycle)]

# Hardcoded episodes (flat), each references a show via show_id (the show slug)
episodes = []

# The Ben Shapiro Show: 30 episodes, starting with "downloaded"
for i in range(1, 31):
    episodes.append({
        "id": i,
        "show_id": 1,
        "uuid": f"uuid-{i}",
        "dw_id": f"dw-{i}",
        "title": f"The Ben Shapiro Show — Episode {i}",
        "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "status": _status_for(0, i),  # downloaded, downloading, processing, error
        "went_live_date": random_datetime(),
        "published_date": random_datetime(),
        "downloaded_date": random_datetime(),
        "redownloaded_date": random_datetime(),
        "created_date": random_datetime(),
        "modified_date": random_datetime()
    })

# The Matt Walsh Show: 20 episodes, starting with "processing"
for i in range(1, 21):
    episodes.append({
        "id": i,
        "show_id": 2,
        "uuid": f"uuid-{i}",
        "dw_id": f"dw-{i}",
        "title": f"The Matt Walsh Show — Episode {i}",
        "description": "Consectetur adipiscing elit.",
        "status": _status_for(2, i),  # processing, error, downloaded, downloading
        "went_live_date": random_datetime(),
        "published_date": random_datetime(),
        "downloaded_date": random_datetime(),
        "redownloaded_date": random_datetime(),
        "created_date": random_datetime(),
        "modified_date": random_datetime()
    })

# Ben After Dark: 7 episodes, starting with "processing"
for i in range(1, 8):
    episodes.append({
        "id": i,
        "show_id": 3,
        "uuid": f"uuid-{i}",
        "dw_id": f"dw-{i}",
        "title": f"Ben After Dark — Episode {i}",
        "index": i,
        "status": _status_for(2, i),
        "went_live_date": random_datetime(),
        "published_date": random_datetime(),
        "downloaded_date": random_datetime(),
        "redownloaded_date": random_datetime(),
        "created_date": random_datetime(),
        "modified_date": random_datetime()
    })
