from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models.ShowLocalAsset import ShowLocalAsset
from backend.utils.show_asset_files import ArtworkConflict, asset_file_hash
from task_manager.tasks.workers.reconcile_show_assets import service


@pytest.fixture
def writer(tmp_path, monkeypatch):
    # Isolate the ownership table while preserving its actual ORM mapping and
    # foreign keys. Parent rows only establish identities for this worker test.
    metadata = sa.MetaData()
    shows = sa.Table("shows", metadata, sa.Column("id", sa.Integer, primary_key=True))
    profiles = sa.Table("local_media_profiles", metadata, sa.Column("id", sa.Integer, primary_key=True))
    ShowLocalAsset.__table__.to_metadata(metadata)
    engine = sa.create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(shows.insert(), [{"id": 1}, {"id": 2}])
        connection.execute(profiles.insert(), [{"id": 1}, {"id": 2}])

    state = SimpleNamespace(
        active_sessions=0, requests=0, media_paths=[],
        image=b"prepared jpeg bytes", current_root=tmp_path / "show",
    )

    class WorkerSession:
        def __init__(self, session):
            self.session = session

        def __getattr__(self, name):
            return getattr(self.session, name)

        def get(self, model, key):
            if model is service.Show:
                return SimpleNamespace(id=key)
            if model is service.ShowLocalMediaProfile:
                return SimpleNamespace(id=key, output_template="template", download_show_assets=True)
            return self.session.get(model, key)

        def scalars(self, statement):
            if list(statement.selected_columns.keys()) == ["file_path"]:
                return state.media_paths
            return self.session.scalars(statement)

    @contextmanager
    def session_scope():
        state.active_sessions += 1
        session = Session(engine)
        try:
            yield WorkerSession(session)
        finally:
            # Deliberately no implicit commit, just like controller.db_utils.
            session.close()
            state.active_sessions -= 1

    def download(_url, workspace, *, ffmpeg_path, check_cancelled):
        assert state.active_sessions == 0, "HTTP must not pin a database transaction"
        check_cancelled()
        state.requests += 1
        path = workspace / "asset.jpg"
        path.write_bytes(state.image)
        return path

    monkeypatch.setattr(service, "db_session", session_scope)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(download_settings=SimpleNamespace(ffmpeg_path="ffmpeg")))
    monkeypatch.setattr(service, "_current", lambda *_: True)
    monkeypatch.setattr(service, "show_profile_roots", lambda *_: {})
    monkeypatch.setattr(service, "managed_show_profile_pairs", lambda *_: {(1, 1), (1, 2)})
    monkeypatch.setattr(service, "show_assets_enabled", lambda _: True)
    monkeypatch.setattr(service, "resolve_show_media_directory", lambda *_: SimpleNamespace(path=str(state.current_root)))
    monkeypatch.setattr(service, "download_show_asset_jpeg", download)
    plan = service.AssetPlan(1, 1, "poster", "https://example.invalid/poster", state.current_root / "poster.jpg", tmp_path, "template")
    state.engine, state.plan = engine, plan
    yield state
    engine.dispose()


def _active():
    pass


def _rows(writer):
    with Session(writer.engine) as session:
        return list(session.scalars(sa.select(ShowLocalAsset)))


def test_download_ownership_is_durable_and_refresh_is_idempotent(writer):
    assert service._refresh_asset(writer.plan, _active)
    rows = _rows(writer)
    assert len(rows) == 1
    assert rows[0].content_hash == asset_file_hash(writer.plan.target)
    assert rows[0].pending_hash is None
    assert rows[0].source_url == writer.plan.url
    assert service._refresh_asset(writer.plan, _active)
    assert writer.requests == 1


def test_profiles_sharing_one_show_directory_share_artwork_without_redownloading(writer):
    service._refresh_asset(writer.plan, _active)
    service._refresh_asset(replace(writer.plan, profile_id=2), _active)
    rows = _rows(writer)
    assert {row.local_media_profile_id for row in rows} == {1, 2}
    assert len({row.content_hash for row in rows}) == 1
    assert writer.requests == 1


def test_other_shows_cannot_claim_existing_artwork(writer):
    service._refresh_asset(writer.plan, _active)
    with pytest.raises(ArtworkConflict, match="Another show"):
        service._refresh_asset(replace(writer.plan, show_id=2), _active)
    assert writer.requests == 1


def test_preexisting_custom_artwork_is_never_adopted(writer):
    writer.plan.target.parent.mkdir()
    writer.plan.target.write_bytes(b"custom poster")
    with pytest.raises(ArtworkConflict, match="User-supplied"):
        service._refresh_asset(writer.plan, _active)
    assert writer.requests == 0
    assert not _rows(writer)


def test_external_modifications_and_alternate_formats_are_preserved(writer):
    service._refresh_asset(writer.plan, _active)
    writer.plan.target.write_bytes(b"edited poster")
    with pytest.raises(ArtworkConflict, match="edited"):
        service._refresh_asset(writer.plan, _active)
    writer.plan.target.with_suffix(".png").write_bytes(b"custom png")
    with pytest.raises(ArtworkConflict, match="alternate-format"):
        service._refresh_asset(writer.plan, _active)
    assert writer.plan.target.read_bytes() == b"edited poster"


def test_upstream_url_change_refreshes_owned_file(writer):
    service._refresh_asset(writer.plan, _active)
    writer.image = b"updated jpeg bytes"
    updated = replace(writer.plan, url="https://example.invalid/new-poster")
    service._refresh_asset(updated, _active)
    assert writer.plan.target.read_bytes() == writer.image
    assert _rows(writer)[0].source_url == updated.url
    assert writer.requests == 2


def test_expired_same_url_is_checked_again(writer, monkeypatch):
    service._refresh_asset(writer.plan, _active)
    monkeypatch.setattr(service, "_REFRESH_AFTER", timedelta(seconds=-1))
    writer.image = b"changed in place"
    service._refresh_asset(writer.plan, _active)
    assert writer.requests == 2
    assert writer.plan.target.read_bytes() == writer.image


def test_failure_after_atomic_replace_is_recoverable_from_pending_hash(writer, monkeypatch):
    publish = service.publish_show_asset

    def interrupted(*args, **kwargs):
        publish(*args, **kwargs)
        raise RuntimeError("process interrupted after publication")

    monkeypatch.setattr(service, "publish_show_asset", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        service._refresh_asset(writer.plan, _active)
    row = _rows(writer)[0]
    assert row.pending_hash == asset_file_hash(writer.plan.target)
    assert row.content_hash is None
    monkeypatch.setattr(service, "publish_show_asset", publish)
    service._refresh_asset(writer.plan, _active)
    row = _rows(writer)[0]
    assert row.content_hash == asset_file_hash(writer.plan.target)
    assert row.pending_hash is None


def test_stale_profile_after_download_does_not_publish(writer, monkeypatch):
    answers = iter((True, False))
    monkeypatch.setattr(service, "_current", lambda *_: next(answers))
    assert service._refresh_asset(writer.plan, _active) is False
    assert not writer.plan.target.exists()
    assert not _rows(writer)


def test_network_failure_keeps_previous_artwork(writer, monkeypatch):
    service._refresh_asset(writer.plan, _active)
    original = writer.plan.target.read_bytes()

    def fail(*args, **kwargs):
        assert writer.active_sessions == 0
        raise OSError("network unavailable")

    monkeypatch.setattr(service, "download_show_asset_jpeg", fail)
    with pytest.raises(OSError):
        service._refresh_asset(replace(writer.plan, url="https://example.invalid/new"), _active)
    assert writer.plan.target.read_bytes() == original
    assert _rows(writer)[0].pending_hash is None


def test_old_root_waits_for_media_rename_and_valid_replacement(writer):
    service._refresh_asset(writer.plan, _active)
    old = writer.plan.target
    writer.current_root = old.parent.parent / "renamed show"
    new_plan = replace(writer.plan, target=writer.current_root / "poster.jpg")
    # Do not remove the old copy before there is a managed replacement.
    service._cleanup_old_roots(1, 1, writer.current_root, writer.plan.download_root, _active)
    assert old.exists()
    service._refresh_asset(new_plan, _active)
    writer.media_paths = [str(old.parent / "possibly externally renamed.mp4")]
    service._cleanup_old_roots(1, 1, writer.current_root, writer.plan.download_root, _active)
    assert old.exists()
    writer.media_paths = [str(writer.current_root / "episode.mp4")]
    service._cleanup_old_roots(1, 1, writer.current_root, writer.plan.download_root, _active)
    assert not old.exists()
    assert new_plan.target.exists()
    assert len(_rows(writer)) == 1


def test_relocation_preserves_artwork_still_owned_by_another_profile(writer):
    service._refresh_asset(writer.plan, _active)
    service._refresh_asset(replace(writer.plan, profile_id=2), _active)
    old = writer.plan.target
    writer.current_root = old.parent.parent / "renamed show"
    service._refresh_asset(replace(writer.plan, target=writer.current_root / "poster.jpg"), _active)
    service._cleanup_old_roots(1, 1, writer.current_root, writer.plan.download_root, _active)
    assert old.exists()
    assert {(row.local_media_profile_id, row.file_path) for row in _rows(writer)} == {
        (1, str(writer.current_root / "poster.jpg")), (2, str(old)),
    }
