from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _new_session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


@pytest.mark.parametrize(
    ("preferred_format", "expected_extension"),
    [
        ("format_4k", "mp4"),
        ("format_1080p", "mp4"),
        ("format_720p", "mp4"),
        ("format_hls", "m3u8"),
        ("format_audio_only", "m4a"),
    ],
)
def test_preferred_format_file_extension(
    preferred_format: str,
    expected_extension: str,
) -> None:
    from backend.types.local_media_profile_types import PreferredFormat

    assert PreferredFormat(preferred_format).file_extension == expected_extension


def test_local_media_profile_models_are_polymorphic_and_unique_by_type() -> None:
    from backend.db.models import (
        LocalMediaProfileBase,
        MovieLocalMediaProfile,
        ShowLocalMediaProfile,
    )

    session, engine = _new_session()
    shared_settings = {
        "output_template": "/downloads/library/{{ title }}.ext",
        "preferred_format": "format_1080p",
    }
    show_profile = ShowLocalMediaProfile(
        slug="show-video", name="Show video", **shared_settings,
    )
    movie_profile = MovieLocalMediaProfile(
        slug="movie-video", name="Movie video", **shared_settings,
    )
    session.add_all([show_profile, movie_profile])
    session.commit()

    profiles = session.query(LocalMediaProfileBase).order_by(LocalMediaProfileBase.id).all()
    assert isinstance(profiles[0], ShowLocalMediaProfile)
    assert isinstance(profiles[1], MovieLocalMediaProfile)
    assert [profile.type for profile in profiles] == ["show", "movie"]

    # Download behavior is not part of the profile identity. The same type,
    # output template and preferred format must remain unique even when the
    # storage-mode override differs.
    session.add(ShowLocalMediaProfile(
        slug="duplicate-show-video",
        name="Duplicate show video",
        download_mode="temporary",
        **shared_settings,
    ))
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
    session.close()
    engine.dispose()


def test_local_media_profile_api_enforces_type_specific_formats_and_placeholders() -> None:
    from backend.api.models.movie_local_media_profile import MovieLocalMediaProfileAPICreate
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    movie = MovieLocalMediaProfileAPICreate(
        type="movie",
        name="Movie 1080p",
        output_template="/downloads/movies/{{ movie_extended_title }}/{{ title }}.ext",
        preferred_format="format_1080p",
    )
    assert movie.type == "movie"
    assert movie.output_template == "/downloads/movies/{{ movie_extended_title }}/{{ title }}.ext"

    with pytest.raises(ValidationError, match="require a video format"):
        MovieLocalMediaProfileAPICreate(
            name="Movie audio",
            output_template="/downloads/movies/{{ movie_slug }}.ext",
            preferred_format="format_audio_only",
        )

    hls_show = ShowLocalMediaProfileAPICreate(
        name="Podcast HLS",
        output_template="/downloads/podcasts/{{ show }}/{{ episode }}.ext",
        preferred_format="format_hls",
    )
    assert hls_show.preferred_format == "format_hls"

    with pytest.raises(ValidationError, match="normal video format"):
        MovieLocalMediaProfileAPICreate(
            name="Movie HLS",
            output_template="/downloads/movies/{{ movie_slug }}/{{ title }}.ext",
            preferred_format="format_hls",
        )

    with pytest.raises(ValidationError, match="episode"):
        MovieLocalMediaProfileAPICreate(
            name="Wrong movie template",
            output_template="/downloads/movies/{{ episode }}.ext",
            preferred_format="format_720p",
        )

    with pytest.raises(ValidationError, match="dw_id"):
        MovieLocalMediaProfileAPICreate(
            name="Rotating ID template",
            output_template="/downloads/movies/{{ movie_title }}/{{ dw_id }}.ext",
            preferred_format="format_1080p",
        )

    with pytest.raises(ValidationError, match="movie_dw_id"):
        MovieLocalMediaProfileAPICreate(
            name="Rotating parent ID template",
            output_template="/downloads/movies/{{ movie_dw_id }}/{{ title }}.ext",
            preferred_format="format_1080p",
        )

    with pytest.raises(ValidationError, match="movie"):
        ShowLocalMediaProfileAPICreate(
            name="Wrong show template",
            output_template="/downloads/shows/{{ movie_slug }}.ext",
            preferred_format="format_audio_only",
        )


def test_local_media_profile_service_rejects_duplicate_and_colliding_outputs() -> None:
    from backend.api.endpoints.movie_local_media_profiles.service import (
        create_movie_local_media_profile,
    )
    from backend.api.endpoints.show_local_media_profiles.service import (
        create_show_local_media_profile,
        update_show_local_media_profile,
    )
    from backend.api.models.movie_local_media_profile import (
        MovieLocalMediaProfileAPICreate,
    )
    from backend.api.models.show_local_media_profile import (
        ShowLocalMediaProfileAPICreate,
        ShowLocalMediaProfileAPIUpdate,
    )

    session, engine = _new_session()
    common = {
        "output_template": "/downloads/library/{{ title }}.ext",
        "preferred_format": "format_1080p",
    }
    show = create_show_local_media_profile(
        session,
        ShowLocalMediaProfileAPICreate(name="Show", **common),
    )
    movie = create_movie_local_media_profile(
        session,
        MovieLocalMediaProfileAPICreate(name="Movie", **common),
    )
    assert show.type == "show"
    assert movie.type == "movie"

    # Exact uniqueness remains type + output template + preferred format. A
    # different Local Media Profile storage override does not make it unique.
    with pytest.raises(HTTPException) as exact_error:
        create_show_local_media_profile(
            session,
            ShowLocalMediaProfileAPICreate(
                type="show",
                name="Duplicate",
                download_mode="temporary",
                **common,
            ),
        )
    assert exact_error.value.status_code == 409
    assert "output path template and preferred format" in exact_error.value.detail[0]["msg"]

    # A different Jinja string that renders to the same path is also a conflict.
    equivalent_template = (
        "{% set media_title = title %}"
        "/downloads/library/{{ media_title }}.ext"
    )
    with pytest.raises(HTTPException) as semantic_error:
        create_show_local_media_profile(
            session,
            ShowLocalMediaProfileAPICreate(
                type="show",
                name="Equivalent",
                output_template=equivalent_template,
                preferred_format="format_1080p",
            ),
        )
    assert semantic_error.value.status_code == 409
    assert semantic_error.value.detail[0]["type"] == "output_path_collision"
    assert "same file as Local Media Profile 'Show'" in semantic_error.value.detail[0]["msg"]

    # Video qualities still resolve to the same concrete .mp4 path, so they may
    # not share an effective output even though preferred_format differs.
    with pytest.raises(HTTPException) as video_quality_error:
        create_show_local_media_profile(
            session,
            ShowLocalMediaProfileAPICreate(
                type="show",
                name="Show 720p",
                output_template=common["output_template"],
                preferred_format="format_720p",
            ),
        )
    assert video_quality_error.value.status_code == 409
    assert video_quality_error.value.detail[0]["type"] == "output_path_collision"

    # Audio and video may safely use the same template because their concrete
    # output extensions differ.
    audio = create_show_local_media_profile(
        session,
        ShowLocalMediaProfileAPICreate(
            name="Show audio",
            output_template=common["output_template"],
            preferred_format="format_audio_only",
        ),
    )
    assert audio.preferred_format == "format_audio_only"

    hls = create_show_local_media_profile(
        session,
        ShowLocalMediaProfileAPICreate(
            name="Show adaptive HLS",
            output_template=common["output_template"],
            preferred_format="format_hls",
        ),
    )
    assert hls.preferred_format == "format_hls"

    distinct = create_show_local_media_profile(
        session,
        ShowLocalMediaProfileAPICreate(
            name="Distinct",
            output_template="/downloads/distinct/{{ title }}.ext",
            preferred_format="format_1080p",
        ),
    )
    with pytest.raises(HTTPException) as update_error:
        update_show_local_media_profile(
            session,
            distinct.slug,
            ShowLocalMediaProfileAPIUpdate(
                type="show",
                name="Distinct",
                output_template=equivalent_template,
                preferred_format="format_1080p",
            ),
        )
    assert update_error.value.status_code == 409
    assert update_error.value.detail[0]["type"] == "output_path_collision"

    session.close()
    engine.dispose()


def test_movie_output_template_uses_movie_metadata(tmp_path: Path, monkeypatch) -> None:
    from backend.db.models import Movie
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_movie_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    movie = Movie(
        uuid="movie-uuid",
        type=MediaType.MOVIE.value,
        slug="a-movie",
        title="A Movie",
        extended_title="A Movie | A Daily Wire Original",
        author_name="A Director",
        mature_rating="PG-13",
        description=None,
        duration=5400,
    )

    result = resolve_movie_output_path(
        "/downloads/{{ movie_author }}/{{ movie_extended_title }} [{{ rating }}]/{{ movie_slug }}.ext",
        movie=movie,
        extension="mp4",
    )

    assert result == (
        tmp_path
        / "A Director"
        / "A Movie _ A Daily Wire Original [PG-13]"
        / "a-movie.mp4"
    ).resolve()


def test_manual_downloads_reject_the_wrong_local_media_profile_type() -> None:
    from backend.api.endpoints.podcast_download_profiles.service import create_download_profile_podcast
    from backend.api.endpoints.media_downloads.service import (
        create_episode_download,
        create_movie_download,
    )
    from backend.api.models.media_download import EpisodeDownloadAPICreate, MovieDownloadAPICreate
    from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPICreate
    from backend.db.models import (
        Episode,
        MovieLocalMediaProfile,
        Season,
        Show,
        ShowLocalMediaProfile,
    )
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid
    from dailywire_api.records import DwMovieRecord

    session, engine = _new_session()
    show_profile = ShowLocalMediaProfile(
        slug="shows",
        name="Shows",
        output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
        preferred_format="format_1080p",
    )
    movie_profile = MovieLocalMediaProfile(
        slug="movies",
        name="Movies",
        output_template="/downloads/movies/{{ movie_slug }}.ext",
        preferred_format="format_1080p",
    )
    show = Show(
        uuid="show-uuid",
        slug="show",
        title="Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="ep-1",
        title="Episode 1",
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/ep-1",
    )
    session.add_all([show_profile, movie_profile, show, season, episode])
    session.commit()

    with pytest.raises(HTTPException, match="Show Local Media Profile") as episode_error:
        create_episode_download(
            session,
            episode.slug,
            EpisodeDownloadAPICreate(local_media_profile_id=movie_profile.id),
        )
    assert episode_error.value.status_code == 422

    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        sharing_url="https://example.test/a-movie",
    )
    with pytest.raises(HTTPException, match="Movie Local Media Profile") as movie_error:
        create_movie_download(
            session,
            movie_data,
            MovieDownloadAPICreate(local_media_profile_id=show_profile.id),
        )
    assert movie_error.value.status_code == 422

    with pytest.raises(HTTPException, match="Show Local Media Profile") as profile_error:
        create_download_profile_podcast(
            session,
            PodcastDownloadProfileAPICreate(
                show_id=show.id,
                local_media_profile_id=movie_profile.id,
                enable_profile=True,
                ep_id_type_list=[],
                download_with_countdown=False,
                redownload_final=False,
                download_days_in_past=0,
                delete_older_episodes=False,
            ),
        )
    assert profile_error.value.status_code == 422

    session.close()
    engine.dispose()
