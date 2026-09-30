from datetime import datetime, timedelta
from types import SimpleNamespace


class _FakeQuery:
    def __init__(self, rows, *, offset=0, limit=None):
        self._rows = rows
        self._offset = offset
        self._limit = limit

    def filter(self, *_args, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def offset(self, value):
        return _FakeQuery(self._rows, offset=value, limit=self._limit)

    def limit(self, value):
        return _FakeQuery(self._rows, offset=self._offset, limit=value)

    def all(self):
        end = None if self._limit is None else self._offset + self._limit
        return self._rows[self._offset:end]


class _FakeSession:
    def __init__(self, episodes):
        self._episodes = episodes

    def query(self, model):
        from backend.db.models import Episode

        if model is Episode:
            return _FakeQuery(self._episodes)
        return _FakeQuery([])


def _episode(index: int, published: datetime):
    return SimpleNamespace(
        id=index,
        show_id=1,
        episode_type="ep",
        publish_status="published_final",
        is_no_show_today=False,
        published_date=published,
        went_live_date=None,
        created_at=published,
    )


def _profile(max_items: int):
    return SimpleNamespace(
        show_id=1,
        use_downloads=False,
        use_dw_stream=True,
        preferred_format="format_1080p",
        prefer_exact_match=False,
        ep_id_type_list=["ep"],
        video_output_mode="mp4",
        stream_live_episodes=False,
        live_episode_handoff_ids=[],
        max_items=max_items,
    )


def test_feed_limit_keeps_newest_items():
    from backend.api.endpoints.feeds.service import get_feed_items

    now = datetime(2026, 1, 1, 12, 0, 0)
    episodes = [_episode(index, now - timedelta(days=index)) for index in range(5)]

    items = get_feed_items(_FakeSession(episodes), _profile(2))

    assert [episode.id for episode, _ in items] == [0, 1]


def test_zero_feed_limit_keeps_full_history():
    from backend.api.endpoints.feeds.service import get_feed_items

    now = datetime(2026, 1, 1, 12, 0, 0)
    episodes = [_episode(index, now - timedelta(days=index)) for index in range(5)]

    items = get_feed_items(_FakeSession(episodes), _profile(0))

    assert [episode.id for episode, _ in items] == [0, 1, 2, 3, 4]


def test_feed_limit_scans_past_ineligible_newest_items():
    from backend.api.endpoints.feeds.service import get_feed_items

    now = datetime(2026, 1, 1, 12, 0, 0)
    episodes = [_episode(index, now - timedelta(minutes=index)) for index in range(60)]
    for episode in episodes[:55]:
        episode.publish_status = "dw_processing"

    items = get_feed_items(_FakeSession(episodes), _profile(2))

    assert [episode.id for episode, _ in items] == [55, 56]
