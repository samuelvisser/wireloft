from datetime import datetime, timedelta
from types import SimpleNamespace


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


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
        require_exact_match=False,
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
