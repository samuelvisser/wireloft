from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_profile_reconciliation_reloads_current_enabled_state():
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from backend.db.models import LocalMediaProfile, PodcastDownloadProfile, Show
    from backend.types.download_profile_types import EpIdType
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from task_manager.tasks.helpers.download_profiles import lock_enabled_download_profile

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
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
        local_media_profile = LocalMediaProfile(
            slug="audio",
            name="Audio",
            output_template="/downloads/{{ show }}/{{ episode }}.ext",
            preferred_format="format_audio_only",
        )
        session.add_all([show, local_media_profile])
        session.flush()
        profile = PodcastDownloadProfile(
            show_id=show.id,
            local_media_profile_id=local_media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            download_with_countdown=False,
            redownload_final=False,
            download_days_in_past=0,
            download_episode_count=0,
            delete_older_episodes=False,
        )
        session.add(profile)
        session.commit()

        # Keep an intentionally stale enabled object in this worker session.
        assert profile.enable_profile is True
        with Session(engine) as other:
            current = other.get(PodcastDownloadProfile, profile.id)
            assert current is not None
            current.enable_profile = False
            other.commit()

        assert profile.enable_profile is True

        # Reconciliation must refresh under the profile lock instead of trusting
        # the object discovered before the concurrent disable committed.
        assert lock_enabled_download_profile(session, profile.id) is None
        assert profile.enable_profile is False
        session.rollback()
    finally:
        session.close()
        engine.dispose()
