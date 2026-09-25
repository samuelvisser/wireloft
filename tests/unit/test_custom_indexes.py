from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from config import get_settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    yield session
    session.close()
    engine.dispose()


def _make_show(session, *, slug="index-show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Index Show",
        description="Description",
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


def _make_season(session, show):
    from backend.db.models import Season

    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add(season)
    session.flush()
    return season


def _make_episode(session, show, season, *, index: int, slug: str, identifier: str):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=identifier,
        slug=slug,
        title=slug.replace("-", " ").title(),
        duration=100.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/{slug}",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session.add(episode)
    session.flush()
    return episode


def _make_profile(session, *, template: str):
    from backend.db.models import ShowLocalMediaProfile

    profile = ShowLocalMediaProfile(
        slug="indexed-video",
        name="Indexed video",
        output_template=template,
        preferred_format="format_1080p",
        show_scope="both",
    )
    session.add(profile)
    session.flush()
    return profile


def _make_download(session, episode, profile, *, file_path=""):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path=file_path,
    )
    session.add(download)
    session.flush()
    return download


def _define(show, *definitions: tuple[str, str]):
    from backend.utils.custom_index import IndexingValueDefinition, replace_indexing_value_definitions

    replace_indexing_value_definitions(
        show,
        [IndexingValueDefinition(key=key, name=name) for key, name in definitions],
    )


def test_indexing_value_definitions_accept_api_models_and_serialize(db_session):
    from backend.api.models.custom_metadata import IndexingValueDefinitionAPI
    from backend.api.models.show import ShowAPIRead
    from backend.utils.custom_index import (
        get_indexing_value_definitions,
        replace_indexing_value_definitions,
    )

    show = _make_show(db_session)
    replace_indexing_value_definitions(
        show,
        [IndexingValueDefinitionAPI(key="featurettes", name="Featurettes")],
    )
    db_session.flush()

    assert get_indexing_value_definitions(show)[0].key == "featurettes"
    payload = ShowAPIRead.model_validate(show)
    assert [(item.key, item.name) for item in payload.indexing_values] == [
        ("featurettes", "Featurettes"),
    ]


def test_custom_index_requires_literal_key():
    from backend.utils.output_template import output_template_custom_index_keys

    assert output_template_custom_index_keys(
        "/downloads/{{ 'featurettes' | custom_index }}/{{ episode }}.ext"
    ) == {"featurettes"}

    with pytest.raises(ValueError, match="literal key"):
        output_template_custom_index_keys(
            "/downloads/{{ episode_type | custom_index }}/{{ episode }}.ext"
        )


def test_custom_indexes_are_persistent_monotonic_media_download_assignments(db_session):
    from backend.services.custom_indexes import ensure_media_download_custom_indexes
    from backend.utils.custom_index import get_media_download_index_assignments

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ show }}/{{ 'extras' | custom_index }}-{{ episode }}.ext",
    )
    _define(show, ("extras", "Extras"))

    episode_100 = _make_episode(db_session, show, season, index=100, slug="episode-100", identifier="ep.100")
    episode_300 = _make_episode(db_session, show, season, index=300, slug="episode-300", identifier="ep.300")
    first = _make_download(db_session, episode_100, profile)
    second = _make_download(db_session, episode_300, profile)

    ensure_media_download_custom_indexes(db_session, download=first, profile=profile, episode=episode_100)
    ensure_media_download_custom_indexes(db_session, download=second, profile=profile, episode=episode_300)
    db_session.commit()

    assert get_media_download_index_assignments(first) == {"extras": 1}
    assert get_media_download_index_assignments(second) == {"extras": 2}

    # Discovering an older episode later never re-ranks existing assignments.
    episode_200 = _make_episode(db_session, show, season, index=200, slug="episode-200", identifier="ep.200")
    third = _make_download(db_session, episode_200, profile)
    ensure_media_download_custom_indexes(db_session, download=third, profile=profile, episode=episode_200)
    db_session.commit()

    assert get_media_download_index_assignments(first) == {"extras": 1}
    assert get_media_download_index_assignments(second) == {"extras": 2}
    assert get_media_download_index_assignments(third) == {"extras": 3}

    # A template that stops using the sequence does not delete old assignments.
    profile.output_template = "/downloads/{{ show }}/{{ episode }}.ext"
    ensure_media_download_custom_indexes(db_session, download=first, profile=profile, episode=episode_100)
    assert get_media_download_index_assignments(first) == {"extras": 1}


def test_custom_index_allocates_only_the_runtime_jinja_branch(db_session):
    from backend.services.custom_indexes import ensure_media_download_custom_indexes
    from backend.utils.custom_index import get_media_download_index_assignments

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template=(
            "{% if episode_type == 'trailer' %}"
            "/downloads/{{ show }}/{{ 'trailers' | custom_index }}-{{ episode }}.ext"
            "{% else %}"
            "/downloads/{{ show }}/{{ 'episodes' | custom_index }}-{{ episode }}.ext"
            "{% endif %}"
        ),
    )
    _define(show, ("trailers", "Trailers"), ("episodes", "Episodes"))

    trailer = _make_episode(db_session, show, season, index=1, slug="trailer-1", identifier="trailer.1")
    episode = _make_episode(db_session, show, season, index=2, slug="episode-1", identifier="ep.1")
    trailer_download = _make_download(db_session, trailer, profile)
    episode_download = _make_download(db_session, episode, profile)

    ensure_media_download_custom_indexes(
        db_session,
        download=trailer_download,
        profile=profile,
        episode=trailer,
    )
    ensure_media_download_custom_indexes(
        db_session,
        download=episode_download,
        profile=profile,
        episode=episode,
    )

    assert get_media_download_index_assignments(trailer_download) == {"trailers": 1}
    assert get_media_download_index_assignments(episode_download) == {"episodes": 1}


def test_undefined_custom_index_renders_empty_and_creates_nothing(db_session):
    from backend.services.custom_indexes import ensure_media_download_custom_indexes
    from backend.utils.custom_index import get_media_download_index_assignments
    from backend.utils.output_template import resolve_episode_output_path

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ 'missing' | custom_index }}-{{ episode }}.ext",
    )
    episode = _make_episode(db_session, show, season, index=1, slug="episode-1", identifier="ep.1")
    download = _make_download(db_session, episode, profile)

    ensure_media_download_custom_indexes(db_session, download=download, profile=profile, episode=episode)
    db_session.commit()

    assert get_media_download_index_assignments(download) == {}
    path = resolve_episode_output_path(
        profile.output_template,
        episode=episode,
        local_media_profile=profile,
        media_download=download,
        extension="mp4",
    )
    assert path.name == "-episode-1.mp4"


def test_defined_custom_index_requires_assignment_before_render(db_session):
    from backend.utils.custom_index import CustomIndexNotReadyError
    from backend.utils.output_template import resolve_episode_output_path

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ 'all' | custom_index }}-{{ episode }}.ext",
    )
    _define(show, ("all", "All episodes"))
    episode = _make_episode(db_session, show, season, index=1, slug="episode-1", identifier="ep.1")
    download = _make_download(db_session, episode, profile)

    with pytest.raises(CustomIndexNotReadyError, match="not ready"):
        resolve_episode_output_path(
            profile.output_template,
            episode=episode,
            local_media_profile=profile,
            media_download=download,
            extension="mp4",
        )


def test_preview_uses_next_value_provisionally_without_reserving_it(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import get_output_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview
    from backend.db.models import CustomIndexState
    from backend.services.custom_indexes import ensure_media_download_custom_indexes
    from backend.utils.output_template import episode_output_template_values

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext",
    )
    _define(show, ("extras", "Extras"))
    episode = _make_episode(db_session, show, season, index=1, slug="episode-1", identifier="ep.1")

    body = LocalMediaProfileTemplatePreview(
        type="show",
        output_template=profile.output_template,
        preferred_format=profile.preferred_format,
        values=episode_output_template_values(episode),
        source_id=f"episode:{episode.id}",
        local_media_profile_id=profile.id,
    )
    preview = get_output_template_preview(db_session, body)

    assert preview.output_path.endswith("/1-episode-1.mp4")
    assert preview.provisional_indexing_values == ["extras"]
    assert db_session.scalar(select(CustomIndexState).limit(1)) is None

    download = _make_download(db_session, episode, profile)
    ensure_media_download_custom_indexes(db_session, download=download, profile=profile, episode=episode)
    db_session.commit()

    preview = get_output_template_preview(db_session, body)
    assert preview.output_path.endswith("/1-episode-1.mp4")
    assert preview.provisional_indexing_values == []


def test_reconcile_existing_downloads_is_deterministic_and_never_reindexes(db_session):
    from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
    from backend.utils.custom_index import get_media_download_index_assignments

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext",
    )
    _define(show, ("extras", "Extras"))

    later = _make_episode(db_session, show, season, index=20, slug="later", identifier="ep.20")
    earlier = _make_episode(db_session, show, season, index=10, slug="earlier", identifier="ep.10")
    later_download = _make_download(db_session, later, profile)
    earlier_download = _make_download(db_session, earlier, profile)

    result = reconcile_show_profile_custom_indexes(
        db_session,
        show_id=show.id,
        local_media_profile_id=profile.id,
    )
    db_session.commit()

    assert result.assignments_created == 2
    assert get_media_download_index_assignments(earlier_download) == {"extras": 1}
    assert get_media_download_index_assignments(later_download) == {"extras": 2}

    rerun = reconcile_show_profile_custom_indexes(
        db_session,
        show_id=show.id,
        local_media_profile_id=profile.id,
    )
    assert rerun.assignments_created == 0
    assert get_media_download_index_assignments(earlier_download) == {"extras": 1}
    assert get_media_download_index_assignments(later_download) == {"extras": 2}


def test_removing_definition_deletes_assignments_and_resets_that_sequence(db_session):
    from backend.db.models import CustomIndexState
    from backend.services.custom_indexes import (
        ensure_media_download_custom_indexes,
        remove_show_indexing_value_assignments,
    )
    from backend.utils.custom_index import (
        get_media_download_index_assignments,
        replace_indexing_value_definitions,
    )

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext",
    )
    _define(show, ("extras", "Extras"))
    first_episode = _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    first_download = _make_download(db_session, first_episode, profile)
    ensure_media_download_custom_indexes(
        db_session,
        download=first_download,
        profile=profile,
        episode=first_episode,
    )
    db_session.commit()
    assert get_media_download_index_assignments(first_download) == {"extras": 1}

    replace_indexing_value_definitions(show, [])
    remove_show_indexing_value_assignments(
        db_session,
        show_id=show.id,
        keys={"extras"},
    )
    db_session.commit()

    assert get_media_download_index_assignments(first_download) == {}
    assert db_session.scalar(
        select(CustomIndexState).where(
            CustomIndexState.show_id == show.id,
            CustomIndexState.key == "extras",
        )
    ) is None

    _define(show, ("extras", "Extras again"))
    ensure_media_download_custom_indexes(
        db_session,
        download=first_download,
        profile=profile,
        episode=first_episode,
    )
    assert get_media_download_index_assignments(first_download) == {"extras": 1}


def test_batch_file_rename_rollback_restores_cycle_without_overwrite(db_session, monkeypatch):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_episode_output_path
    from task_manager.tasks.workers.rename_show_profile_files.service import run_rename_show_profile_files

    show = _make_show(db_session, slug="rollback-show")
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ show }}/{{ episode }}.ext",
    )
    first = _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    second = _make_episode(db_session, show, season, index=2, slug="second", identifier="ep.2")

    first_expected = resolve_episode_output_path(
        profile.output_template,
        episode=first,
        local_media_profile=profile,
        extension="mp4",
    )
    second_expected = resolve_episode_output_path(
        profile.output_template,
        episode=second,
        local_media_profile=profile,
        extension="mp4",
    )
    first_expected.parent.mkdir(parents=True, exist_ok=True)
    second_expected.write_bytes(b"first episode")
    first_expected.write_bytes(b"second episode")

    first_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=first.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(second_expected),
    )
    second_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=second.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(first_expected),
    )
    db_session.add_all([first_download, second_download])
    db_session.commit()

    real_commit = db_session.commit
    commit_count = 0

    def fail_second_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("forced database commit failure")
        real_commit()

    monkeypatch.setattr(db_session, "commit", fail_second_commit)
    with pytest.raises(RuntimeError, match="forced database commit failure"):
        run_rename_show_profile_files(
            db_session,
            show_id=show.id,
            local_media_profile_id=profile.id,
        )

    assert first_expected.read_bytes() == b"second episode"
    assert second_expected.read_bytes() == b"first episode"


def test_batch_file_rename_stages_source_destination_cycle(db_session):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_episode_output_path
    from task_manager.tasks.workers.rename_show_profile_files.service import run_rename_show_profile_files

    show = _make_show(db_session, slug="rename-show")
    season = _make_season(db_session, show)
    profile = _make_profile(
        db_session,
        template="/downloads/{{ show }}/{{ episode }}.ext",
    )
    first = _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    second = _make_episode(db_session, show, season, index=2, slug="second", identifier="ep.2")

    first_expected = resolve_episode_output_path(
        profile.output_template,
        episode=first,
        local_media_profile=profile,
        extension="mp4",
    )
    second_expected = resolve_episode_output_path(
        profile.output_template,
        episode=second,
        local_media_profile=profile,
        extension="mp4",
    )
    first_expected.parent.mkdir(parents=True, exist_ok=True)
    second_expected.write_bytes(b"first episode")
    first_expected.write_bytes(b"second episode")

    first_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=first.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(second_expected),
    )
    second_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=second.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(first_expected),
    )
    db_session.add_all([first_download, second_download])
    db_session.commit()

    result = run_rename_show_profile_files(
        db_session,
        show_id=show.id,
        local_media_profile_id=profile.id,
    )

    assert result.data["files_renamed"] == 2
    assert first_expected.read_bytes() == b"first episode"
    assert second_expected.read_bytes() == b"second episode"
    db_session.refresh(first_download)
    db_session.refresh(second_download)
    assert first_download.file_path == str(first_expected)
    assert second_download.file_path == str(second_expected)
