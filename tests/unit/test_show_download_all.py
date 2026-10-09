from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def library(monkeypatch):
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier

    # No downloads execute during these unit tests; queued operations remain inspectable.
    monkeypatch.setattr(
        "task_manager.tasks.media_download_operations.dispatch_queued_media_download_operations",
        lambda _session: 0,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        def add_show(slug: str, show_type: str):
            show = Show(
                uuid=f"{slug}-uuid",
                slug=slug,
                title=slug,
                description="",
                sharing_url=f"https://example.test/{slug}",
                membership_level="FREE",
                type=show_type,
                episode_identifier=(
                    EpisodeIdentifier.SEASONAL.value
                    if show_type == "series"
                    else EpisodeIdentifier.NUMBERED.value
                ),
                author_name="Host",
                author_slug="host",
            )
            session.add(show)
            session.flush()
            return show

        def add_season(show, index: int):
            season = Season(
                show=show,
                index=index,
                slug=f"season-{index}",
                name=f"Season {index}",
            )
            session.add(season)
            session.flush()
            return season

        def add_episode(show, season, index: int, identifier: str, status: str = "published_final"):
            episode = Episode(
                uuid=f"{show.slug}-{index}-uuid",
                type=MediaType.EPISODE.value,
                show=show,
                season=season,
                index=index,
                episode_identifier=identifier,
                slug=f"{show.slug}-episode-{index}",
                title=f"Episode {index}",
                description="",
                duration=60,
                publish_status=status,
                sharing_url=f"https://example.test/{show.slug}/{index}",
                published_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
            session.add(episode)
            session.flush()
            return episode

        def add_profile(name: str, scope: str = "both"):
            profile = LocalMediaProfile(
                slug=name,
                name=name,
                output_template=f"/downloads/{{{{ show }}}}/{name}/{{{{ episode }}}}.ext",
                preferred_format="format_audio_only",
                show_scope=scope,
            )
            session.add(profile)
            session.flush()
            return profile

        yield session, add_show, add_season, add_episode, add_profile
    engine.dispose()


def _dependencies(session, operation_id):
    from task_manager.scheduler.db import TaskOperationDependency

    return list(session.scalars(
        select(TaskOperationDependency)
        .where(TaskOperationDependency.parent_operation_id == operation_id)
        .order_by(TaskOperationDependency.id)
    ))


def _request(profile_id: int, *, seasons=(), types=()):
    from backend.api.models.show import ShowDownloadAllAPIRequest

    return ShowDownloadAllAPIRequest(
        local_media_profile_id=profile_id,
        season_ids=list(seasons),
        episode_types=list(types),
    )


def test_podcast_download_all_uses_episode_types_and_skips_downloaded_files(library):
    from backend.api.endpoints.shows.service import request_show_download_all
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.media_types import MediaType
    from task_manager.scheduler.db import TaskOperation
    from task_manager.scheduler.types import OperationSource

    session, add_show, add_season, add_episode, add_profile = library
    show = add_show("podcast", "podcast")
    season = add_season(show, 1)
    normal = add_episode(show, season, 1, "ep.1")
    extra = add_episode(show, season, 2, "ep-extra.other.1.1")
    add_episode(show, season, 3, "aux.1")
    add_episode(show, season, 4, "ep.4", status="scheduled")
    profile = add_profile("audio")
    already_downloaded = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=normal.id,
        local_media_profile_id=profile.id,
        artifact_status="available",
        file_path="/downloads/podcast/existing.mp3",
    )
    session.add(already_downloaded)
    session.flush()

    result = request_show_download_all(
        session, show.slug, _request(profile.id, types=["ep", "ep-extra"]),
    )

    parent = session.get(TaskOperation, result["operation_id"])
    dependencies = _dependencies(session, result["operation_id"])
    assert result["queued"] is True
    assert result["episodes_queued"] == 1
    assert parent.kind == "show.download_all"
    assert parent.context["local_media_profile_id"] == profile.id
    assert len(dependencies) == 1
    child = dependencies[0].child_operation
    assert child.kind == "media.download"
    assert child.source == OperationSource.UI.value
    assert child.context["is_redownload"] is False
    download = session.get(EpisodeMediaDownload, child.resource_id)
    assert download.media_item_id == extra.id
    assert download.local_media_profile_id == profile.id
    assert already_downloaded.artifact_status == "available"


def test_series_download_all_selects_seasons_independently_of_current_page(library):
    from backend.api.endpoints.shows.service import request_show_download_all
    from backend.db.models.media_download import EpisodeMediaDownload

    session, add_show, add_season, add_episode, add_profile = library
    show = add_show("series", "series")
    first = add_season(show, 1)
    second = add_season(show, 2)
    add_episode(show, first, 1, "ep.S01E01")
    selected_episode = add_episode(show, second, 2, "ep.S02E01")
    profile = add_profile("video", "series")

    result = request_show_download_all(
        session, show.slug, _request(profile.id, seasons=[second.id]),
    )
    dependencies = _dependencies(session, result["operation_id"])

    assert result["episodes_queued"] == 1
    assert len(dependencies) == 1
    download = session.get(EpisodeMediaDownload, dependencies[0].child_operation.resource_id)
    assert download.media_item_id == selected_episode.id


def test_download_all_does_not_restart_existing_active_download(library):
    from backend.api.endpoints.shows.service import request_show_download_all
    from task_manager.scheduler.types import OperationDependencyCancelPolicy

    session, add_show, add_season, add_episode, add_profile = library
    show = add_show("podcast", "podcast")
    season = add_season(show, 1)
    add_episode(show, season, 1, "ep.1")
    profile = add_profile("audio")

    first = request_show_download_all(session, show.slug, _request(profile.id, types=["ep"]))
    second = request_show_download_all(session, show.slug, _request(profile.id, types=["ep"]))
    first_dependency = _dependencies(session, first["operation_id"])[0]
    second_dependency = _dependencies(session, second["operation_id"])[0]

    assert second["episodes_queued"] == 1
    assert first_dependency.child_operation_id == second_dependency.child_operation_id
    assert second_dependency.cancel_policy == OperationDependencyCancelPolicy.DETACH.value


def test_download_all_retries_missing_artifact_without_replacing_other_profiles(library):
    from backend.api.endpoints.shows.service import request_show_download_all
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.media_types import MediaType

    session, add_show, add_season, add_episode, add_profile = library
    show = add_show("podcast", "podcast")
    season = add_season(show, 1)
    episode = add_episode(show, season, 1, "ep.1")
    selected_profile = add_profile("selected")
    unrelated_profile = add_profile("unrelated")
    missing = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=selected_profile.id,
        artifact_status="missing",
        file_path="/downloads/podcast/missing.mp3",
    )
    unaffected = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=unrelated_profile.id,
        artifact_status="available",
        file_path="/downloads/podcast/unrelated.mp3",
    )
    session.add_all([missing, unaffected])
    session.flush()

    result = request_show_download_all(
        session, show.slug, _request(selected_profile.id, types=["ep"]),
    )

    dependencies = _dependencies(session, result["operation_id"])
    assert result["episodes_queued"] == 1
    assert dependencies[0].child_operation.resource_id == missing.id
    assert dependencies[0].child_operation.context["is_redownload"] is True
    assert dependencies[0].child_operation.context["prepare_existing_artifact"] is True
    assert missing.artifact_status == "missing"
    assert unaffected.artifact_status == "available"


def test_download_all_is_noop_when_selected_episodes_are_downloaded(library):
    from backend.api.endpoints.shows.service import request_show_download_all
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.media_types import MediaType

    session, add_show, add_season, add_episode, add_profile = library
    show = add_show("podcast", "podcast")
    season = add_season(show, 1)
    episode = add_episode(show, season, 1, "ep.1")
    profile = add_profile("audio")
    session.add(EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status="available",
        file_path="/downloads/podcast/ep1.mp3",
    ))
    session.flush()

    result = request_show_download_all(session, show.slug, _request(profile.id, types=["ep"]))
    assert result["queued"] is False
    assert result["episodes_queued"] == 0
    assert _dependencies(session, result["operation_id"]) == []


def test_download_all_requires_one_profile_and_rejects_invalid_filters(library):
    from backend.api.endpoints.shows.service import request_show_download_all
    from backend.api.models.show import ShowDownloadAllAPIRequest

    session, add_show, add_season, add_episode, add_profile = library
    podcast = add_show("podcast", "podcast")
    season = add_season(podcast, 1)
    add_episode(podcast, season, 1, "ep.1")
    series = add_show("series", "series")
    series_season = add_season(series, 1)
    add_episode(series, series_season, 1, "ep.S01E01")
    incompatible_profile = add_profile("podcast-only", "podcast")
    profile = add_profile("any")

    for data in ({"episodeTypes": ["ep"]}, {"localMediaProfileId": None, "episodeTypes": ["ep"]}):
        with pytest.raises(ValidationError):
            ShowDownloadAllAPIRequest.model_validate(data)

    with pytest.raises(ValidationError):
        _request(profile.id, types=["all"])

    requests = (
        (podcast.slug, _request(profile.id)),
        (podcast.slug, _request(profile.id, seasons=[season.id], types=["ep"])),
        (series.slug, _request(profile.id)),
        (series.slug, _request(profile.id, seasons=[season.id])),
        (series.slug, _request(incompatible_profile.id, seasons=[series_season.id])),
    )
    for slug, body in requests:
        with pytest.raises(HTTPException) as exc:
            request_show_download_all(session, slug, body)
        assert exc.value.status_code == 422
