from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def _library(session: Session):
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="show-uuid",
        slug="test-show",
        title="Test Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    episode = Episode(
        uuid="episode-uuid",
        type=MediaType.EPISODE.value,
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="episode-1",
        title="Episode 1",
        description=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/episode-1",
    )
    audio_profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    video_profile = LocalMediaProfile(
        slug="video",
        name="Video",
        output_template="/downloads/{{ show }}/video/{{ episode }}.ext",
        preferred_format="format_1080p",
    )
    session.add_all([show, season, episode, audio_profile, video_profile])
    session.flush()

    audio_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=audio_profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path="/downloads/audio.m4a",
    )
    video_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=video_profile.id,
        artifact_status=MediaDownloadArtifactStatus.MISSING.value,
        file_path="/downloads/video.mp4",
    )
    session.add_all([audio_download, video_download])
    session.commit()
    return show, episode, audio_profile, video_profile, audio_download, video_download


def test_episode_download_scope_can_be_reused_for_profile_and_artifact_selection():
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.utils.episode_download_scope import EpisodeDownloadScope

    session, engine = _session()
    try:
        (
            show,
            episode,
            audio_profile,
            video_profile,
            audio_download,
            video_download,
        ) = _library(session)

        scope = EpisodeDownloadScope.resolve(session, show_id=show.id)

        assert scope.show.id == show.id
        assert scope.episode is None
        assert scope.local_media_profile_ids == tuple(sorted((audio_profile.id, video_profile.id)))
        assert scope.local_media_profile_count == 2
        assert scope.episode_ids == (episode.id,)
        assert {download.id for download in scope.downloads} == {
            audio_download.id,
            video_download.id,
        }

        audio_scope = scope.select(local_media_profile_id=audio_profile.id)
        assert audio_scope.local_media_profile_ids == (audio_profile.id,)
        assert [download.id for download in audio_scope.downloads] == [audio_download.id]
        assert audio_scope.result_data()["local_media_profiles"] == 1

        available_scope = scope.select(
            artifact_statuses=(MediaDownloadArtifactStatus.AVAILABLE.value,),
        )
        assert [download.id for download in available_scope.downloads] == [audio_download.id]
    finally:
        session.close()
        engine.dispose()


def test_episode_download_scope_resolves_single_episode_and_all_profiles():
    from backend.utils.episode_download_scope import EpisodeDownloadScope

    session, engine = _session()
    try:
        show, episode, _audio_profile, _video_profile, _audio_download, _video_download = _library(session)

        scope = EpisodeDownloadScope.resolve(session, episode_id=episode.id)

        assert scope.show.id == show.id
        assert scope.episode is not None
        assert scope.episode.id == episode.id
        assert len(scope.downloads) == 2
        assert scope.result_data()["episode_slug"] == episode.slug
    finally:
        session.close()
        engine.dispose()
