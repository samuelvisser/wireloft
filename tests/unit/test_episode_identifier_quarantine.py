from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _record(number: int):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{number}",
        slug=f"replacement-{number}",
        title=f"Episode {number}",
        description=None,
        duration=3600,
        episode_number=f"{number}.00",
        display_episode_number=str(number),
        background_image_path=None,
        sharing_url=f"https://example.test/{number}",
        publish_status="PUBLISHED",
        is_downloadable=True,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 9, 7, 10, tzinfo=timezone.utc),
        scheduled_date=None,
    )


def test_reclaimed_head_advances_rolled_back_numbered_counter():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.mapper import _identify_with_vacated_reclaims

    replacement = _record(2500)
    mapped, values = _identify_with_vacated_reclaims(
        identifier_type=EpisodeIdentifier.NUMBERED,
        episodes=[replacement],
        current_values={
            "ep_id.latest_ep_num": 2499,
            "ep_id.latest_ep_extra_num": 7,
            "ep_id.latest_aux_num": 3,
        },
        season=SimpleNamespace(index=1),
        vacated_identifiers={"ep.2500"},
    )

    assert mapped == [("ep.2500", replacement)]
    assert values["ep_id.latest_ep_num"] == 2500
    assert values["ep_id.latest_ep_extra_num"] == 0
    assert values["ep_id.latest_aux_num"] == 3


def test_reclaimed_older_identifier_never_rewinds_newer_counter():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.mapper import _identify_with_vacated_reclaims

    replacement = _record(2500)
    mapped, values = _identify_with_vacated_reclaims(
        identifier_type=EpisodeIdentifier.NUMBERED,
        episodes=[replacement],
        current_values={
            "ep_id.latest_ep_num": 2501,
            "ep_id.latest_ep_extra_num": 2,
        },
        season=SimpleNamespace(index=1),
        vacated_identifiers={"ep.2500"},
    )

    assert mapped == [("ep.2500", replacement)]
    assert values["ep_id.latest_ep_num"] == 2501
    assert values["ep_id.latest_ep_extra_num"] == 2


@pytest.mark.parametrize(
    ("initial_counter", "expected_identifiers"),
    [
        (None, {"not-usable.1", "not-usable.2", "not-usable.3", "not-usable.4"}),
        ("4", {"not-usable.5", "not-usable.6", "not-usable.7", "not-usable.8"}),
    ],
)
def test_quarantine_identifier_reservation_is_atomic_across_sessions(
    tmp_path,
    initial_counter,
    expected_identifiers,
):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Episode, Season, Show
    from backend.types.episode_types import EpisodePublishStatus
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid
    from task_manager.tasks.helpers.episodes.quarantine import quarantine_episode_identifier

    database_path = tmp_path / "quarantine-concurrency.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")

        with Session(engine) as session:
            show = Show(
                uuid="concurrent-show-uuid",
                slug="concurrent-show",
                title="Concurrent Show",
                description=None,
                sharing_url="https://example.test/show",
                membership_level="FREE",
                type=ShowType.PODCAST.value,
                episode_identifier=EpisodeIdentifier.NUMBERED.value,
                author_name="Host",
                author_slug="host",
            )
            season = Season(show=show, index=1, slug="season-1", name="One")
            session.add_all([show, season])
            session.flush()
            if initial_counter is not None:
                show.set_meta("ep_id.latest_not_usable_num", initial_counter)

            episode_ids = []
            for index in range(1, 5):
                episode = Episode(
                    uuid=generate_uuid(),
                    type="episode",
                    show=show,
                    season=season,
                    index=index,
                    episode_identifier=f"ep-extra.1.{index}",
                    slug=f"concurrent-episode-{index}",
                    title=f"Concurrent episode {index}",
                    duration=100.0,
                    publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
                    sharing_url=f"https://example.test/concurrent-{index}",
                    published_date=datetime(2026, 9, 7, 10, index, tzinfo=timezone.utc).replace(tzinfo=None),
                )
                session.add(episode)
                session.flush()
                episode_ids.append(episode.id)
            show_id = show.id
            session.commit()

        barrier = Barrier(len(episode_ids))

        def quarantine(episode_id: int) -> str:
            with Session(engine) as session:
                episode = session.get(Episode, episode_id)
                assert episode is not None

                # Reproduce production: each worker has its own Session and may
                # already have the same old show metadata snapshot in memory.
                list(episode.show.meta_items)
                barrier.wait(timeout=10)

                assert quarantine_episode_identifier(session, episode) is True
                identifier = episode.episode_identifier
                session.commit()
                return identifier

        with ThreadPoolExecutor(max_workers=len(episode_ids)) as executor:
            identifiers = set(executor.map(quarantine, episode_ids))

        assert identifiers == expected_identifiers

        with Session(engine) as session:
            stored_identifiers = set(session.scalars(
                select(Episode.episode_identifier).where(Episode.show_id == show_id)
            ))
            assert stored_identifiers == expected_identifiers
            stored_show = session.get(Show, show_id)
            assert stored_show is not None
            assert stored_show.get_meta("ep_id.latest_not_usable_num") == str(
                max(int(value.rsplit(".", 1)[1]) for value in expected_identifiers)
            )
    finally:
        engine.dispose()
