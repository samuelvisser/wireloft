from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    session = Session(engine)
    Base.metadata.create_all(engine)
    yield session
    session.close()
    engine.dispose()


def _make_show(session: Session, slug: str = "show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Show",
        description=None,
        sharing_url=f"https://example.test/{slug}",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_local_media_profile(session: Session, slug: str):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug=slug,
        name=slug,
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_1080p",
    )
    session.add(profile)
    session.flush()
    return profile


def _make_download_profile(session: Session, show, local_media_profile, episode_types: list[str]):
    from backend.db.models.download_profile import PodcastDownloadProfile

    profile = PodcastDownloadProfile(
        show=show,
        local_media_profile=local_media_profile,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=episode_types,
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=0,
        delete_older_episodes=False,
    )
    session.add(profile)
    session.flush()
    return profile


def _make_episode(session: Session, show):
    from backend.db.models import Episode, Season

    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    episode = Episode(
        uuid="episode-uuid",
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="episode-1",
        title="Episode 1",
        duration=100,
        publish_status="published_final",
        sharing_url="https://example.test/episode-1",
        is_no_show_today=False,
    )
    session.add_all([season, episode])
    session.flush()
    return episode


def test_same_show_and_media_profile_allows_non_overlapping_episode_types(db_session: Session):
    show = _make_show(db_session)
    local_media_profile = _make_local_media_profile(db_session, "video")

    episode_profile = _make_download_profile(db_session, show, local_media_profile, ["ep"])
    auxiliary_profile = _make_download_profile(db_session, show, local_media_profile, ["aux"])

    assert episode_profile.id != auxiliary_profile.id


def test_overlapping_episode_type_is_rejected_for_same_show_and_media_profile(db_session: Session):
    from backend.api.endpoints.download_profiles.service import require_unique_download_profile_episode_types

    show = _make_show(db_session)
    local_media_profile = _make_local_media_profile(db_session, "video")
    _make_download_profile(db_session, show, local_media_profile, ["ep"])

    with pytest.raises(HTTPException) as exc_info:
        require_unique_download_profile_episode_types(
            db_session,
            show_id=show.id,
            local_media_profile_id=local_media_profile.id,
            episode_types=["ep", "aux"],
        )

    assert exc_info.value.status_code == 409
    assert "ep" in str(exc_info.value.detail)


def test_episode_type_can_be_reused_with_different_media_profile(db_session: Session):
    from backend.api.endpoints.download_profiles.service import require_unique_download_profile_episode_types

    show = _make_show(db_session)
    first_media_profile = _make_local_media_profile(db_session, "video-1080")
    second_media_profile = _make_local_media_profile(db_session, "video-720")
    _make_download_profile(db_session, show, first_media_profile, ["ep"])

    require_unique_download_profile_episode_types(
        db_session,
        show_id=show.id,
        local_media_profile_id=second_media_profile.id,
        episode_types=["ep"],
    )


def test_profile_update_does_not_conflict_with_its_own_episode_types(db_session: Session):
    from backend.api.endpoints.download_profiles.service import require_unique_download_profile_episode_types

    show = _make_show(db_session)
    local_media_profile = _make_local_media_profile(db_session, "video")
    profile = _make_download_profile(db_session, show, local_media_profile, ["ep", "aux"])

    require_unique_download_profile_episode_types(
        db_session,
        show_id=show.id,
        local_media_profile_id=local_media_profile.id,
        episode_types=["ep", "aux"],
        exclude_profile_id=profile.id,
    )


def test_existing_download_moves_to_profile_that_now_owns_episode_type(db_session: Session):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    local_media_profile = _make_local_media_profile(db_session, "video")
    previous_profile = _make_download_profile(db_session, show, local_media_profile, ["aux"])
    current_profile = _make_download_profile(db_session, show, local_media_profile, ["ep"])
    episode = _make_episode(db_session, show)

    download = EpisodeMediaDownload(
        type="episode",
        media_item_id=episode.id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=previous_profile.id,
        download_status=MediaDownloadStatus.DOWNLOADED.value,
        file_path="/downloads/episode.mp4",
        progress=100,
        downloaded_publish_status="published_final",
    )
    db_session.add(download)
    db_session.flush()

    action = ensure_episode_download(db_session, current_profile, episode)

    assert action.needs_trigger is False
    assert download.download_profile_id == current_profile.id
