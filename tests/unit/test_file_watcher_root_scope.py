from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _download(session: Session, *, path: str):
    from backend.db.models.media_download import MediaDownloadBase
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType

    download = MediaDownloadBase(
        type=MediaType.BASE.value,
        media_item_id=1,
        local_media_profile_id=1,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=path,
    )
    session.add(download)
    session.flush()
    return download


def test_file_watcher_filters_foreign_roots_in_sql(
    db_session, tmp_path, monkeypatch, caplog,
):
    from config import get_settings
    from task_manager.tasks.workers.file_watcher._helpers import get_tracked_downloads

    current_root = tmp_path / "current-downloads"
    current_root.mkdir()
    foreign_root = tmp_path / "other-host" / "downloads"
    monkeypatch.setattr(
        get_settings().download_settings,
        "download_root",
        current_root,
    )

    current = _download(
        db_session,
        path=str(current_root / "shows" / "episode.m4a"),
    )
    foreign = _download(
        db_session,
        path=str(foreign_root / "shows" / "episode.m4a"),
    )
    current_id, foreign_id = current.id, foreign.id
    db_session.commit()
    db_session.expunge_all()

    rows = get_tracked_downloads(
        db_session,
        show_id=None,
        show_slug=None,
    )

    assert [row.id for row in rows] == [current_id]
    assert foreign_id not in {row.id for row in rows}
    assert "skipped 1 artifact(s)" in caplog.text
    assert "outside the configured download root" in caplog.text


def test_file_watcher_preserves_artifacts_when_configured_root_is_unavailable(
    db_session, tmp_path, monkeypatch, caplog,
):
    from config import get_settings
    from task_manager.tasks.workers.file_watcher._helpers import get_tracked_downloads

    unavailable_root = tmp_path / "not-mounted"
    monkeypatch.setattr(
        get_settings().download_settings,
        "download_root",
        unavailable_root,
    )

    _download(
        db_session,
        path=str(unavailable_root / "shows" / "episode.m4a"),
    )
    db_session.commit()
    db_session.expunge_all()

    assert get_tracked_downloads(
        db_session,
        show_id=None,
        show_slug=None,
    ) == []
    assert "configured download root" in caplog.text
    assert "is unavailable" in caplog.text
    assert "left their database state unchanged" in caplog.text
