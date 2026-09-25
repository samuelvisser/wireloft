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


def _define(profile, *definitions: tuple[str, str]):
    from backend.utils.custom_index import IndexingValueDefinition, replace_indexing_value_definitions

    replace_indexing_value_definitions(
        profile,
        [IndexingValueDefinition(key=key, name=name) for key, name in definitions],
    )


def _request(session, show, profile):
    from backend.db.models import CustomIndexState
    state = session.query(CustomIndexState).filter_by(show_id=show.id, local_media_profile_id=profile.id).one_or_none()
    if state is None:
        state = CustomIndexState(show_id=show.id, local_media_profile_id=profile.id)
        session.add(state)
    else:
        state.requested_generation += 1
    session.flush()
    return state


def test_definitions_belong_to_lmp_and_serialize(db_session):
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPIRead
    from backend.utils.custom_index import get_indexing_value_definitions
    show = _make_show(db_session)
    profile = _make_profile(db_session, template="/downloads/{{ episode }}.ext")
    _define(profile, ("featurettes", "Featurettes"))
    db_session.flush()
    assert get_indexing_value_definitions(show) == []
    assert [(value.key, value.name) for value in ShowLocalMediaProfileAPIRead.model_validate(profile).indexing_values] == [("featurettes", "Featurettes")]


def test_custom_index_keys_allow_dashes_end_to_end(db_session):
    from backend.api.models.custom_metadata import IndexingValueDefinitionAPI
    from backend.utils.custom_index import get_indexing_value_definitions
    from backend.utils.output_template import output_template_custom_index_keys

    definition = IndexingValueDefinitionAPI(
        key="behind-the-scenes",
        name="Behind the scenes",
    )
    template = "/downloads/{{ 'behind-the-scenes' | custom_index }}.ext"
    profile = _make_profile(db_session, template=template)
    _define(profile, (definition.key, definition.name))

    assert [(value.key, value.name) for value in get_indexing_value_definitions(profile)] == [
        ("behind-the-scenes", "Behind the scenes"),
    ]
    assert output_template_custom_index_keys(template) == {"behind-the-scenes"}


def test_custom_index_requires_literal_key():
    from backend.utils.output_template import output_template_custom_index_keys
    assert output_template_custom_index_keys("/downloads/{{ 'featurettes' | custom_index }}.ext") == {"featurettes"}
    with pytest.raises(ValueError, match="literal key"):
        output_template_custom_index_keys("/downloads/{{ episode_type | custom_index }}.ext")


def test_conditional_paths_can_select_distinct_index_directories():
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS, SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        validate_output_template_path_requirements,
    )

    template = ("{% if episode_type == 'trailer' %}"
                "{% set number = 'extras' | custom_index %}"
                "/downloads/Extras/{{ number }}.ext"
                "{% else %}"
                "{% set number = 'featurettes' | custom_index %}"
                "/downloads/Featurettes/{{ number }}.ext"
                "{% endif %}")
    assert validate_output_template_path_requirements(
        template, allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    ) == template


def test_reconciliation_uses_every_episode_and_reorders_historical_discovery(db_session):
    from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
    from backend.utils.custom_index import get_episode_index_assignments
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(db_session, template="/downloads/{{ 'featurettes' | custom_index }}-{{ episode }}.ext")
    _define(profile, ("featurettes", "Featurettes"))
    first = _make_episode(db_session, show, season, index=100, slug="first", identifier="ep.1")
    last = _make_episode(db_session, show, season, index=300, slug="last", identifier="ep.3")
    download = _make_download(db_session, last, profile)
    state = _request(db_session, show, profile)
    result = reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    db_session.flush()
    assert result.episodes_considered == 2
    assert get_episode_index_assignments(first, profile.id) == {"featurettes": 1}
    assert get_episode_index_assignments(last, profile.id) == {"featurettes": 2}
    assert not any(item.key.startswith("custom_index.") for item in download.meta_items)
    assert state.completed_generation == state.requested_generation

    middle = _make_episode(db_session, show, season, index=200, slug="middle", identifier="ep.2")
    _request(db_session, show, profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    assert get_episode_index_assignments(middle, profile.id) == {"featurettes": 2}
    assert get_episode_index_assignments(last, profile.id) == {"featurettes": 3}
    again = reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    assert again.assignments_changed == 0


def test_branches_repeated_calls_and_undefined_key(db_session):
    from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
    from backend.utils.custom_index import get_episode_index_assignments
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    template = """{% if episode_type == 'trailer' %}{% set a = 'featurettes' | custom_index %}{% set b = 'featurettes' | custom_index %}/downloads/{{ a }}-{{ episode }}.ext{% else %}{% set a = 'extras' | custom_index %}{% set missing = 'unknown' | custom_index %}/downloads/{{ a }}-{{ episode }}.ext{% endif %}"""
    profile = _make_profile(db_session, template=template)
    _define(profile, ("featurettes", "Featurettes"), ("extras", "Extras"))
    trailer = _make_episode(db_session, show, season, index=100, slug="trailer", identifier="aux.1")
    featurette = _make_episode(db_session, show, season, index=200, slug="featurette", identifier="trailer.1")
    _request(db_session, show, profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    assert get_episode_index_assignments(trailer, profile.id) == {"extras": 1}
    assert get_episode_index_assignments(featurette, profile.id) == {"featurettes": 1}


def test_removed_definition_and_scope_clean_all_assignments(db_session):
    from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
    from backend.utils.custom_index import get_episode_index_assignments
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    profile = _make_profile(db_session, template="/downloads/{{ 'extras' | custom_index }}.ext")
    _define(profile, ("extras", "Extras"))
    _request(db_session, show, profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    assert get_episode_index_assignments(episode, profile.id) == {"extras": 1}
    _define(profile)
    _request(db_session, show, profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    assert get_episode_index_assignments(episode, profile.id) == {}
    _define(profile, ("extras", "Extras"))
    profile.show_scope = "series"
    _request(db_session, show, profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    assert get_episode_index_assignments(episode, profile.id) == {}


def test_normal_render_requires_current_generation_and_never_allocates(db_session):
    from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
    from backend.utils.custom_index import CustomIndexNotReadyError, get_episode_index_assignments
    from backend.utils.output_template import resolve_episode_output_path
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    profile = _make_profile(db_session, template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext")
    _define(profile, ("extras", "Extras"))
    state = _request(db_session, show, profile)
    with pytest.raises(CustomIndexNotReadyError):
        resolve_episode_output_path(profile.output_template, episode=episode, local_media_profile=profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    before = get_episode_index_assignments(episode, profile.id)
    assert str(resolve_episode_output_path(profile.output_template, episode=episode, local_media_profile=profile)).endswith("1-first.ext")
    assert get_episode_index_assignments(episode, profile.id) == before
    state.requested_generation += 1
    db_session.flush()
    with pytest.raises(CustomIndexNotReadyError):
        resolve_episode_output_path(profile.output_template, episode=episode, local_media_profile=profile)


def test_undefined_index_renders_empty_without_sequence_state(db_session):
    from backend.db.models import CustomIndexState
    from backend.utils.output_template import resolve_episode_output_path

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    profile = _make_profile(db_session, template="/downloads/{{ 'undefined' | custom_index }}-{{ episode }}.ext")
    assert str(resolve_episode_output_path(
        profile.output_template, episode=episode, local_media_profile=profile,
    )).endswith("-first.ext")
    assert db_session.query(CustomIndexState).count() == 0
    assert episode.meta_items == []


def test_profile_save_queues_index_work_before_optional_rename(db_session):
    from backend.api.endpoints.show_local_media_profiles.service import update_show_local_media_profile
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPIUpdate
    from backend.db.models import CustomIndexState
    from task_manager.scheduler.db import TaskOperation

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    _make_episode(db_session, show, season, index=1, slug="first", identifier="ep.1")
    profile = _make_profile(db_session, template="/downloads/{{ episode }}.ext")
    body = ShowLocalMediaProfileAPIUpdate(
        name=profile.name, preferred_format=profile.preferred_format,
        output_template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext",
        show_scope="both", indexing_values=[{"key": "extras", "name": "Extras"}],
    )
    update_show_local_media_profile(db_session, profile.slug, body, rename_files=True)

    operations = list(db_session.query(TaskOperation).all())
    assert [operation.kind for operation in operations] == ["local_media_profile.manage_custom_indexes"]
    assert operations[0].targets[0].task_kwargs["rename_after"] is True
    state = db_session.query(CustomIndexState).one()
    assert (state.show_id, state.local_media_profile_id) == (show.id, profile.id)
    assert state.completed_generation < state.requested_generation


def test_draft_preview_simulates_without_persisting(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import get_output_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview
    from backend.utils.custom_index import get_episode_index_assignments
    from backend.utils.output_template import episode_output_template_values
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    first = _make_episode(db_session, show, season, index=100, slug="first", identifier="ep.1")
    second = _make_episode(db_session, show, season, index=200, slug="second", identifier="ep.2")
    profile = _make_profile(db_session, template="/downloads/{{ episode }}.ext")
    body = LocalMediaProfileTemplatePreview(type="show", output_template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext", preferred_format="format_1080p", values=episode_output_template_values(second), source_id=f"episode:{second.id}", local_media_profile_id=profile.id, indexing_values=[{"key": "extras", "name": "Extras"}])
    preview = get_output_template_preview(db_session, body)
    assert preview.output_path.endswith("2-second.mp4")
    assert get_episode_index_assignments(first, profile.id) == {}
    assert get_episode_index_assignments(second, profile.id) == {}


@pytest.mark.parametrize("was_synchronized", [True, False])
def test_historical_episode_only_queues_rename_for_synchronized_file(db_session, was_synchronized):
    from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.utils.output_template import resolve_episode_output_path

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    profile = _make_profile(db_session, template="/downloads/{{ 'extras' | custom_index }}-{{ episode }}.ext")
    _define(profile, ("extras", "Extras"))
    _make_episode(db_session, show, season, index=100, slug="first", identifier="ep.1")
    last = _make_episode(db_session, show, season, index=300, slug="last", identifier="ep.3")
    _request(db_session, show, profile)
    reconcile_show_profile_custom_indexes(db_session, show_id=show.id, local_media_profile_id=profile.id)
    expected = resolve_episode_output_path(
        profile.output_template, episode=last, local_media_profile=profile, extension="mp4",
    )
    source = expected if was_synchronized else expected.with_name("kept-by-user.mp4")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"video")
    download = _make_download(db_session, last, profile, file_path=str(source))
    download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
    db_session.flush()

    _make_episode(db_session, show, season, index=200, slug="middle", identifier="ep.2")
    _request(db_session, show, profile)
    result = reconcile_show_profile_custom_indexes(
        db_session, show_id=show.id, local_media_profile_id=profile.id,
    )
    assert result.synced_source_paths == (
        ((last.id, str(expected)),) if was_synchronized else ()
    )
    assert source.read_bytes() == b"video"


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
