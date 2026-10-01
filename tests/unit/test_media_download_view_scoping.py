from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_media_download_view_filters_episode_show_and_movie_in_sql():
    import backend.db.models  # noqa: F401

    from backend.api.endpoints.media_downloads.service import get_media_downloads_view
    from backend.db import Base
    from backend.db.models import (
        Episode,
        Movie,
        MovieExtra,
        MovieLocalMediaProfile,
        Season,
        Show,
        ShowLocalMediaProfile,
    )
    from backend.db.models.media_download import (
        EpisodeMediaDownload,
        MovieExtraMediaDownload,
        MovieMediaDownload,
    )
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        show = Show(
            uuid="show-scope",
            slug="scope-show",
            title="Scope Show",
            description=None,
            sharing_url="https://example.test/show",
            membership_level="FREE",
            type=ShowType.PODCAST.value,
            episode_identifier=EpisodeIdentifier.NUMBERED.value,
            author_name="Host",
            author_slug="host",
        )
        season = Season(show=show, index=1, slug="season-1", name="Season 1")
        episode_one = Episode(
            uuid="episode-scope-1",
            type=MediaType.EPISODE.value,
            show=show,
            season=season,
            index=1,
            episode_identifier="ep.1",
            dw_episode_number="1",
            slug="episode-one",
            title="Episode One",
            description=None,
            duration=60,
            publish_status="published_final",
            sharing_url="https://example.test/episode-one",
        )
        episode_two = Episode(
            uuid="episode-scope-2",
            type=MediaType.EPISODE.value,
            show=show,
            season=season,
            index=2,
            episode_identifier="ep.2",
            dw_episode_number="2",
            slug="episode-two",
            title="Episode Two",
            description=None,
            duration=60,
            publish_status="published_final",
            sharing_url="https://example.test/episode-two",
        )
        show_profile = ShowLocalMediaProfile(
            slug="show-profile",
            name="Show Profile",
            output_template="/downloads/{{ episode }}.ext",
            preferred_format="format_audio_only",
        )

        movie = Movie(
            uuid="movie-scope",
            type=MediaType.MOVIE.value,
            slug="scope-movie",
            title="Scope Movie",
            description=None,
            duration=600,
        )
        trailer = MovieExtra(
            uuid="movie-extra-scope",
            type=MediaType.MOVIE_EXTRA.value,
            movie=movie,
            movie_extra_type="trailer",
            slug="scope-trailer",
            title="Scope Trailer",
            description=None,
            duration=30,
        )
        movie_profile = MovieLocalMediaProfile(
            slug="movie-profile",
            name="Movie Profile",
            output_template="/downloads/{{ title }}.ext",
            preferred_format="format_1080p",
        )

        session.add_all([
            show,
            season,
            episode_one,
            episode_two,
            show_profile,
            movie,
            trailer,
            movie_profile,
        ])
        session.flush()

        session.add_all([
            EpisodeMediaDownload(
                type=MediaType.EPISODE.value,
                media_item_id=episode_one.id,
                local_media_profile_id=show_profile.id,
                artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
                file_path="/downloads/episode-one.ext",
                downloaded_publish_status="published_final",
            ),
            EpisodeMediaDownload(
                type=MediaType.EPISODE.value,
                media_item_id=episode_two.id,
                local_media_profile_id=show_profile.id,
                artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
                file_path="/downloads/episode-two.ext",
            ),
            MovieMediaDownload(
                type=MediaType.MOVIE.value,
                media_item_id=movie.id,
                local_media_profile_id=movie_profile.id,
                artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
                file_path="/downloads/movie.ext",
            ),
            MovieExtraMediaDownload(
                type=MediaType.MOVIE_EXTRA.value,
                media_item_id=trailer.id,
                local_media_profile_id=movie_profile.id,
                artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
                file_path="/downloads/trailer.ext",
            ),
        ])
        session.commit()

        [episode_view] = get_media_downloads_view(
            session,
            episode_slug=episode_one.slug,
        )
        assert episode_view.episode_slug == episode_one.slug
        assert episode_view.show_slug == show.slug
        assert episode_view.downloaded_publish_status == "published_final"

        show_views = get_media_downloads_view(session, show_slug=show.slug)
        assert {view.episode_slug for view in show_views} == {
            episode_one.slug,
            episode_two.slug,
        }

        movie_views = get_media_downloads_view(session, movie_slug=movie.slug)
        assert {view.type for view in movie_views} == {
            MediaType.MOVIE.value,
            MediaType.MOVIE_EXTRA.value,
        }
        trailer_view = next(
            view for view in movie_views
            if view.type == MediaType.MOVIE_EXTRA.value
        )
        assert trailer_view.media_slug == trailer.slug
        assert trailer_view.movie_slug == movie.slug

    engine.dispose()
