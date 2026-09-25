from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def test_show_view_maps_nested_orm_source_through_aliases():
    from backend.api.models.show import ShowAPIReadView

    show = SimpleNamespace(
        id=1,
        uuid="show-uuid",
        slug="show",
        membership_level="FREE",
        type="podcast",
        episode_identifier="numbered",
        author_slug="host",
        title="Show",
        description="Description",
        sharing_url="https://example.test/show",
        author_name="Host",
        author_headshot_path=None,
        background_image_path=None,
        logo_image_path=None,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        created_at=NOW,
        updated_at=NOW,
        meta_items=[],
    )
    source = SimpleNamespace(
        show=show,
        episode_count=12,
        years="2025-2026",
    )

    view = ShowAPIReadView.model_validate(source)

    assert view.id == 1
    assert view.title == "Show"
    assert view.episode_count == 12
    assert view.years == "2025-2026"


def test_download_profile_view_uses_relationship_aliases_and_discriminated_impl():
    from backend.api.models.download_profile_view import DownloadProfileAPIReadView
    from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPIRead

    profile = SimpleNamespace(
        id=4,
        show_id=1,
        local_media_profile_id=2,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=["ep", "aux"],
        created_at=NOW,
        updated_at=NOW,
        show=SimpleNamespace(title="Show", slug="show"),
        local_media_profile=SimpleNamespace(name="Audio", preferred_format="audio"),
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=25,
        download_starting_from=None,
        delete_older_episodes=True,
    )

    view = DownloadProfileAPIReadView.model_validate(
        SimpleNamespace(profile=profile)
    )

    assert view.show_title == "Show"
    assert view.local_media_profile_name == "Audio"
    assert isinstance(view.download_profile_impl, PodcastDownloadProfileAPIRead)
    assert view.download_profile_impl.download_episode_count == 25


def test_stream_profile_view_uses_relationship_aliases():
    from backend.api.models.stream_profile import StreamProfileAPIReadView

    profile = SimpleNamespace(
        id=5,
        show_id=1,
        enable_profile=True,
        use_downloads=True,
        use_dw_stream=False,
        preferred_format="audio",
        require_exact_match=False,
        ep_id_type_list=["ep"],
        type="rss",
        created_at=NOW,
        updated_at=NOW,
        show=SimpleNamespace(title="Show", slug="show"),
        feed_url="https://example.test/feed",
        dw_video_method="stream_hls_download_m4a",
        max_items=200,
    )

    view = StreamProfileAPIReadView.model_validate(
        SimpleNamespace(profile=profile, implementation=profile)
    )

    assert view.show_slug == "show"
    assert view.stream_profile_impl.feed_url == "https://example.test/feed"


def test_media_download_view_maps_composed_sources_without_manual_serialization():
    from backend.api.models.media_download import MediaDownloadAPIReadView
    from task_manager.scheduler.types import TaskStatus

    episode = SimpleNamespace(
        slug="episode",
        title="Episode",
        episode_identifier="ep.42",
        show=SimpleNamespace(slug="show", title="Show"),
    )
    download = SimpleNamespace(
        id=7,
        type="episode",
        media_item_id=8,
        local_media_profile_id=9,
        file_path="/downloads/episode.mp4",
        thumbnail_path=None,
        artifact_status="available",
        artifact_error=None,
        automatic_retry_suppressed=False,
        downloaded_bytes=123,
        format_downloaded="1080p",
        downloaded_at=NOW,
        first_successful_download_at=NOW,
        can_delete=False,
        created_at=NOW,
        updated_at=NOW,
        downloaded_publish_status="published_final",
    )
    source = SimpleNamespace(
        download=download,
        media=episode,
        episode=episode,
        movie=None,
        movie_extra=None,
        show=episode.show,
        profile=SimpleNamespace(name="Video", preferred_format="1080p"),
        latest_run=SimpleNamespace(
            status=TaskStatus.SUCCEEDED,
            last_error=None,
            started_at=NOW,
            finished_at=NOW,
        ),
        latest_task_is_redownload=True,
        queue_position=None,
    )

    view = MediaDownloadAPIReadView.model_validate(source)

    assert view.id == 7
    assert view.episode_identifier == "ep.42"
    assert view.show_title == "Show"
    assert view.latest_task_status == TaskStatus.SUCCEEDED.value
    assert view.latest_task_is_redownload is True


def test_task_models_follow_relationship_aliases():
    from backend.api.models.tasks import TaskLedgerEntryRead

    run = SimpleNamespace(
        id=10,
        definition=SimpleNamespace(key="worker"),
        resource_type="show",
        resource_id=3,
        status="SUCCEEDED",
        message="Done",
        last_error=None,
        meta={"inputs": {"refresh": True}},
        result={"summary": "Done"},
        started_at=NOW,
        finished_at=NOW,
        runtime_ms=100,
    )

    item = TaskLedgerEntryRead.model_validate(run)

    assert item.definition_key == "worker"
    assert item.inputs == {"refresh": True}
