from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _episode(*, show, season, index: int, slug: str, published: datetime):
    from backend.db.models.media_item import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from backend.types.media_types import MediaType

    return Episode(
        uuid=f"uuid-{slug}",
        type=MediaType.EPISODE.value,
        show_id=show.id,
        season_id=season.id,
        index=index,
        episode_identifier=f"ep.{index}",
        dw_episode_number=str(index),
        slug=slug,
        publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
        video_url=None,
        audio_url=None,
        sharing_url=f"https://example.test/{slug}",
        went_live_date=None,
        published_date=published,
        scheduled_date=None,
        title=slug,
        description=None,
        duration=60,
        background_image_path=None,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
    )


def test_episode_view_page_is_bounded_and_season_filtered():
    import backend.db.models  # noqa: F401

    from backend.api.endpoints.episodes.service import get_episode_views_by_show_page
    from backend.db import Base
    from backend.db.models import Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        show = Show(
            uuid="show-pagination",
            slug="pagination-show",
            title="Pagination Show",
            description=None,
            sharing_url="https://example.test/show",
            membership_level="FREE",
            type=ShowType.SERIES.value,
            episode_identifier=EpisodeIdentifier.SEASONAL.value,
            author_name="Host",
            author_slug="host",
        )
        session.add(show)
        session.flush()

        season_one = Season(show_id=show.id, index=1, slug="season-1", name="Season 1")
        season_two = Season(show_id=show.id, index=2, slug="season-2", name="Season 2")
        session.add_all([season_one, season_two])
        session.flush()

        session.add_all([
            _episode(
                show=show,
                season=season_one,
                index=1,
                slug="season-1-episode-1",
                published=datetime(2026, 1, 1),
            ),
            _episode(
                show=show,
                season=season_two,
                index=1,
                slug="season-2-episode-1",
                published=datetime(2026, 2, 1),
            ),
            _episode(
                show=show,
                season=season_two,
                index=2,
                slug="season-2-episode-2",
                published=datetime(2026, 2, 2),
            ),
        ])
        session.commit()

        newest = get_episode_views_by_show_page(
            session,
            show.slug,
            offset=0,
            limit=2,
        )
        assert [item.slug for item in newest.items] == [
            "season-2-episode-2",
            "season-2-episode-1",
        ]
        assert newest.total == 3
        assert newest.show_total == 3
        assert newest.has_more is True

        second_season = get_episode_views_by_show_page(
            session,
            show.slug,
            offset=0,
            limit=1,
            season_id=season_two.id,
        )
        assert [item.slug for item in second_season.items] == ["season-2-episode-1"]
        assert second_season.total == 2
        assert second_season.show_total == 3
        assert second_season.has_more is True

        second_page = get_episode_views_by_show_page(
            session,
            show.slug,
            offset=1,
            limit=1,
            season_id=season_two.id,
        )
        assert [item.slug for item in second_page.items] == ["season-2-episode-2"]
        assert second_page.has_more is False

    engine.dispose()



def test_recently_indexed_episode_views_use_index_time_and_limit():
    import backend.db.models  # noqa: F401

    from backend.api.endpoints.episodes.service import get_recently_indexed_episodes
    from backend.db import Base
    from backend.db.models import Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        show = Show(
            uuid="show-recent-indexing",
            slug="recent-indexing-show",
            title="Recent Indexing Show",
            description=None,
            sharing_url="https://example.test/show",
            membership_level="FREE",
            type=ShowType.SERIES.value,
            episode_identifier=EpisodeIdentifier.SEASONAL.value,
            author_name="Host",
            author_slug="host",
        )
        session.add(show)
        session.flush()

        season = Season(show_id=show.id, index=1, slug="season-1", name="Season 1")
        session.add(season)
        session.flush()

        oldest = _episode(
            show=show,
            season=season,
            index=1,
            slug="indexed-oldest",
            published=datetime(2026, 4, 3),
        )
        newest = _episode(
            show=show,
            season=season,
            index=2,
            slug="indexed-newest",
            published=datetime(2026, 4, 1),
        )
        middle = _episode(
            show=show,
            season=season,
            index=3,
            slug="indexed-middle",
            published=datetime(2026, 4, 2),
        )
        oldest.created_at = datetime(2026, 4, 1, 10, 0)
        newest.created_at = datetime(2026, 4, 3, 10, 0)
        middle.created_at = datetime(2026, 4, 2, 10, 0)
        session.add_all([oldest, newest, middle])
        session.commit()

        recent = get_recently_indexed_episodes(session, limit=2)

        assert [item.slug for item in recent] == ["indexed-newest", "indexed-middle"]
        assert [item.show_title for item in recent] == [
            "Recent Indexing Show",
            "Recent Indexing Show",
        ]
        assert [item.show_slug for item in recent] == [
            "recent-indexing-show",
            "recent-indexing-show",
        ]

    engine.dispose()
