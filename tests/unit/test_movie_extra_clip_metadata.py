from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_download_clip_metadata_refresh_updates_canonical_source() -> None:
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource
    from backend.types.media_types import MediaType
    from dailywire_api.records import DwMovieExtraPlaybackRecord
    from task_manager.tasks.workers.download_movie.service import _persist_movie_extra_metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        movie = Movie(
            uuid="movie-clip-refresh",
            type=MediaType.MOVIE.value,
            slug="run-hide-fight",
            title="Run Hide Fight",
            description=None,
            duration=6000,
        )
        extra = MovieExtra(
            uuid="extra-clip-refresh",
            type=MediaType.MOVIE_EXTRA.value,
            movie=movie,
            movie_extra_type="scene",
            slug="mass-shooting-safety-expert-breaks-down-scenes-from-run-hide-fight",
            title="Old title",
            description="Old description",
            duration=1,
            thumbnail_landscape_path="https://example.invalid/stale landscape.png",
            thumbnail_portrait_path="https://example.invalid/stale portrait.png",
            thumbnail_square_path="https://example.invalid/stale square.png",
            sharing_url="https://example.invalid/old",
            available_for=["ALL_ACCESS"],
        )
        session.add_all([movie, extra])
        session.commit()

        thumbnail_url = (
            "https://daily-wire-production.imgix.net/clips/ckk2pibct76em0722atmhheia/"
            "John%20Matthews%20Thumbnail.png?auto=compress&cs=origin"
        )
        playback = DwMovieExtraPlaybackRecord.from_clip_payload(
            {
                "id": "2ce931ff-1fba-48fa-8352-7bc0d9e5efe6",
                "slug": extra.slug,
                "title": "Mass Shooting Safety Expert Breaks Down Scenes From Run Hide Fight",
                "description": "Fresh description",
                "duration": 513.095922,
                "publishedAt": "2026-09-16T19:27:02.570Z",
                "sharingURL": (
                    "https://www.dailywire.com/clips/"
                    "mass-shooting-safety-expert-breaks-down-scenes-from-run-hide-fight"
                ),
                "availableFor": ["FREE", "READER", "ALL_ACCESS"],
                "images": {
                    "thumbnail": {
                        "land": thumbnail_url,
                        "port": thumbnail_url,
                        "square": "",
                    }
                },
                "videoURL": "https://stream.example/extra/master.m3u8",
            },
            video_url="https://stream.example/extra/master.m3u8",
        )

        thumbnail_refreshed, selected_thumbnail = _persist_movie_extra_metadata(
            session,
            extra_id=extra.id,
            metadata=playback.metadata,
        )

        session.expire_all()
        source = session.query(MovieExtraSource).one()
        placement = session.query(MovieExtra).one()

        assert thumbnail_refreshed is True
        assert selected_thumbnail == thumbnail_url
        assert source.title == playback.metadata.title
        assert source.description == "Fresh description"
        assert source.duration == 513.095922
        assert source.thumbnail_landscape_path == thumbnail_url
        assert source.thumbnail_portrait_path == thumbnail_url
        assert source.thumbnail_square_path == ""
        assert source.sharing_url == playback.metadata.sharing_url
        assert source.available_for == ["FREE", "READER", "ALL_ACCESS"]
        assert placement.movie_extra_type == "scene"
    finally:
        session.close()
        engine.dispose()
