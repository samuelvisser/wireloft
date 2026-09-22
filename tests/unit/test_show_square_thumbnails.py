from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_show(session: Session, *, slug: str = "test-show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description=None,
        sharing_url=f"https://www.dailywire.com/show/{slug}",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.commit()
    return show


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def test_dailywire_square_show_thumbnail_lookup_uses_square_carousel(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    payload = {
        "components": [
            {
                "renderType": "portraitShowCarousel",
                "items": [{
                    "show": {
                        "slug": "ignored",
                        "images": {"thumbnail": {"land": "wrong.jpg"}},
                    },
                }],
            },
            {
                "renderType": "squareShowCarousel",
                "items": [
                    {
                        "show": {
                            "slug": "explicit-square",
                            "images": {
                                "thumbnail": {
                                    "square": "square.jpg",
                                    "land": "land.jpg",
                                    "port": "port.jpg",
                                },
                            },
                        },
                    },
                    {
                        "show": {
                            "slug": "land-fallback",
                            "images": {
                                "thumbnail": {
                                    "square": "",
                                    "land": "land-square.jpg",
                                    "port": "port-square.jpg",
                                },
                            },
                        },
                    },
                    {
                        "show": {
                            "slug": "port-fallback",
                            "images": {
                                "thumbnail": {
                                    "square": "",
                                    "land": "",
                                    "port": "port-only-square.jpg",
                                },
                            },
                        },
                    },
                ],
            },
        ],
    }
    captured = {}

    def fake_get(endpoint, params):
        captured["endpoint"] = endpoint
        captured["params"] = params
        return payload

    client = MiddlewareClient(base_url="https://example.invalid", pace_requests=False)
    monkeypatch.setattr(client, "_get", fake_get)

    result = client.get_square_show_thumbnails(membership_plan="ALL_ACCESS")

    assert captured == {
        "endpoint": "v4/getPage",
        "params": {
            "slug": "watch-page",
            "membershipPlan": "ALL_ACCESS",
        },
    }
    assert result == {
        "explicit-square": "square.jpg",
        "land-fallback": "land-square.jpg",
        "port-fallback": "port-only-square.jpg",
    }


def test_dailywire_square_show_thumbnail_lookup_allows_missing_carousel(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    client = MiddlewareClient(base_url="https://example.invalid", pace_requests=False)
    monkeypatch.setattr(
        client,
        "_get",
        lambda _endpoint, _params: {"components": []},
    )

    assert client.get_square_show_thumbnails() == {}


@pytest.mark.parametrize(
    ("remote_thumbnails", "expected"),
    [
        ({"test-show": "square.jpg"}, "square.jpg"),
        ({}, None),
    ],
)
def test_initial_index_saves_square_thumbnail_only_when_show_is_in_carousel(
    db_session,
    monkeypatch,
    remote_thumbnails,
    expected,
):
    from task_manager.tasks.workers.fetch_new_episodes import service

    show = _make_show(db_session)

    class FakeClient:
        def __init__(self):
            self.square_calls = 0

        def get_square_show_thumbnails(self, *, membership_plan=None):
            self.square_calls += 1
            assert membership_plan == "FREE"
            return remote_thumbnails

        def get_show_page(self, _slug, *, membership_plan=None):
            assert membership_plan == "FREE"
            return SimpleNamespace(seasons=[])

    client = FakeClient()
    monkeypatch.setattr(
        service,
        "get_dw_episodes_since_ep",
        lambda *_args, **_kwargs: ({}, {}),
    )
    monkeypatch.setattr(service, "_queue_show_indexed", lambda *_args, **_kwargs: None)

    result = asyncio.run(
        service._fetch_show(
            db_session,
            show=show,
            client=client,
            access_token=None,
            dry_run=False,
            initial_index=True,
        )
    )

    assert result == 0
    assert client.square_calls == 1
    db_session.expire_all()
    assert db_session.get(type(show), show.id).thumbnail_square_path == expected


def test_show_added_marks_episode_scan_as_initial_index():
    from backend.api.endpoints.shows.events import ShowAdded

    event = ShowAdded(
        SimpleNamespace(
            id=7,
            slug="test-show",
            title="Test Show",
        )
    )

    assert event["initial_index"] is True


def test_show_index_operation_persists_initial_index_worker_input():
    from backend.api.endpoints.shows.operations import ShowIndexOperation

    operation = ShowIndexOperation(
        SimpleNamespace(
            id=7,
            slug="test-show",
            title="Test Show",
        )
    )

    [target] = operation.targets()
    assert target.task_kwargs == {"initial_index": True}


class _MigrationContext:
    def __init__(self):
        self.progress = []

    def raise_if_cancelled(self):
        return None

    def update_progress(self, current, total, message=None):
        self.progress.append((current, total, message))


def test_square_thumbnail_background_migration_fetches_watch_page_once(monkeypatch):
    migration = importlib.import_module(
        "backend.db.background_migrations.versions.3c8f6a1d2b47_square_show_thumbnails"
    )

    calls = []
    applied = []

    class FakeClient:
        def __init__(self, *, access_token=None):
            assert access_token is None

        def get_square_show_thumbnails(self):
            calls.append("watch-page")
            return {"matched-show": "square.jpg"}

    monkeypatch.setattr(
        migration,
        "_show_count",
        lambda: 2,
    )
    monkeypatch.setattr(
        migration,
        "_apply_square_thumbnails",
        lambda thumbnails: applied.append(thumbnails) or 1,
    )
    monkeypatch.setattr(
        migration,
        "DeviceAuthClient",
        lambda: SimpleNamespace(get_token=lambda: None),
    )
    monkeypatch.setattr(migration, "MiddlewareClient", FakeClient)

    context = _MigrationContext()
    asyncio.run(migration.migrate(context))

    assert calls == ["watch-page"]
    assert applied == [{"matched-show": "square.jpg"}]
    assert context.progress[0][:2] == (0, 2)
    assert context.progress[-1][:2] == (2, 2)


def test_square_thumbnail_background_migration_leaves_missing_show_empty(
    monkeypatch,
):
    from backend.db import Base
    import backend.db.models  # noqa: F401
    from backend.db.models import Show
    migration = importlib.import_module(
        "backend.db.background_migrations.versions.3c8f6a1d2b47_square_show_thumbnails"
    )
    from backend.types.show_types import EpisodeIdentifier, ShowType

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for slug in ("matched-show", "missing-show"):
            session.add(Show(
                uuid=f"{slug}-uuid",
                slug=slug,
                title=slug,
                description=None,
                sharing_url=f"https://www.dailywire.com/show/{slug}",
                membership_level="FREE",
                type=ShowType.PODCAST.value,
                episode_identifier=EpisodeIdentifier.NUMBERED.value,
                author_name="Host",
                author_slug="host",
            ))
        session.commit()

    monkeypatch.setattr(migration, "get_session", lambda: Session(engine))
    assert migration._apply_square_thumbnails(
        {"matched-show": "square.jpg"}
    ) == 1

    with Session(engine) as session:
        matched = session.query(Show).filter_by(slug="matched-show").one()
        missing = session.query(Show).filter_by(slug="missing-show").one()
        assert matched.thumbnail_square_path == "square.jpg"
        assert missing.thumbnail_square_path is None

    engine.dispose()
