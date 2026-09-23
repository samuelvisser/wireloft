from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_episode_grid_view_uses_landscape_thumbnail():
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.episodes.service import get_episode_views_by_show_list
    from backend.db import Base
    from backend.db.models import Season, Show
    from backend.db.models.media_item import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        show = Show(
            uuid="show-uuid",
            slug="show-slug",
            title="Show",
            description=None,
            sharing_url="https://example.test/show",
            membership_level="FREE",
            type=ShowType.PODCAST.value,
            episode_identifier=EpisodeIdentifier.NUMBERED.value,
            author_name="Host",
            author_slug="host",
        )
        session.add(show)
        session.flush()

        season = Season(
            show_id=show.id,
            index=1,
            slug="2026",
            name="2026",
        )
        session.add(season)
        session.flush()

        session.add(Episode(
            uuid="episode-uuid",
            type=MediaType.EPISODE.value,
            show_id=show.id,
            season_id=season.id,
            index=1,
            episode_identifier="ep.1",
            dw_episode_number="1",
            slug="episode-1",
            publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
            video_url=None,
            audio_url=None,
            sharing_url="https://example.test/episode-1",
            went_live_date=None,
            published_date=None,
            scheduled_date=None,
            title="Episode",
            description=None,
            duration=60,
            background_image_path=None,
            thumbnail_landscape_path="landscape.jpg",
            thumbnail_portrait_path="portrait.jpg",
            thumbnail_square_path="square.jpg",
        ))
        session.commit()

        [episode] = get_episode_views_by_show_list(session, show.slug)

        assert episode.thumbnail_landscape_path == "landscape.jpg"
        assert not hasattr(episode, "thumbnail_portrait_path")

    engine.dispose()
