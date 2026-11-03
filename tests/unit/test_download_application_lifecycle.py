from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from dailywire_downloader.lifecycle import DownloadTracker
from dailywire_downloader.models import DownloadProgress, DownloadResult
from dailywire_downloader.plan import ResolvedDownloadSource, SidecarSpec, build_download_plan


@pytest.fixture
def library(task_database, monkeypatch):
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition
    from test_media_download_operations import _make_download
    with task_database() as session:
        Base.metadata.create_all(session.bind)
        for key in ('download_episode', 'download_movie'):
            session.add(TaskDefinition(key=key, title=key, allowed_resource_types=['media_download'], default_max_retries=0))
        first = _make_download(session, slug='main')
        second = _make_download(session, slug='extra')
        first.downloaded_bytes, second.downloaded_bytes = 900, 100
        first.media.description = second.media.description = 'Description'
        session.commit()
        ids = (first.id, second.id)
    from task_manager.tasks import download_adapter
    monkeypatch.setattr(download_adapter, 'on_media_download_transfer_complete', lambda: None)
    return task_database, ids


def start_run(factory, download_id):
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.scheduler.operations import create_operation, OperationTargetSpec
    with factory() as session:
        definition = session.scalar(select(TaskDefinition).where(TaskDefinition.key == 'download_episode'))
        run = TaskRun(definition_id=definition.id, resource_type=ResourceType.MEDIA_DOWNLOAD,
                      resource_id=download_id, status=TaskStatus.RUNNING, progress=0,
                      attempt_count=1, max_retries=0, started_at=datetime.now(timezone.utc))
        session.add(run)
        session.flush()
        operation = create_operation(session, kind='media.download', source='UI', resource_type='media_download', resource_id=download_id,
            title='Test download', targets=[OperationTargetSpec('download_episode', 'media_download', download_id)])
        session.commit()
        return run.id, operation.id


def test_artifacts_history_and_execution_commit_atomically(library, tmp_path, monkeypatch):
    from backend.db.models.media_download import MediaDownloadBase, MediaDownloadHistory
    from backend.api.models.media_download import MediaDownloadAPIRead
    from dailywire_downloader import coordinator
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import ProgressUpdater, _PreparedExecution, _finalize_execution
    from task_manager.scheduler.operations import get_operation
    from task_manager.scheduler.operation_context import operation_context
    from task_manager.scheduler.operation_control import cancel_operation, cancel_task_run
    from task_manager.tasks import download_adapter
    factory, (download_id, _) = library
    run_id, operation_id = start_run(factory, download_id)
    def prepare(session, _download_id, tracker):
        session.rollback()
        return build_download_plan(source=ResolvedDownloadSource('https://media.test/file.mp4','1080p',False,False,'mp4',False,expected_bytes=100),
            requested_destination=tmp_path/'library'/'Movie.mp4', temporary_root=tmp_path/'temp',download_mode='temporary',
            assets=(SidecarSpec('nfo','nfo',content=b'<movie/>',extension='nfo'),),attempt_id=tracker.attempt_id)
    monkeypatch.setattr(download_adapter,'prepare_download_plan',prepare)
    def download(_url,path,*,progress,should_cancel):
        Path(path).write_bytes(b'x'*100)
        progress(DownloadProgress(100,100))
        return DownloadResult(path,100)
    monkeypatch.setattr(coordinator,'download_file',download)
    with factory() as session, operation_context((operation_id,)):
        result = download_adapter.run_download(session,media_download_id=download_id,progress=ProgressUpdater(run_id))
    operation = get_operation(operation_id)
    assert operation.status == 'SUCCEEDED'
    with factory() as session:
        record = session.get(MediaDownloadBase,download_id)
        assert record.artifact_status == 'available'
        assert Path(record.assets[0].path).read_bytes() == b'<movie/>'
        api_download = MediaDownloadAPIRead.model_validate(record)
        assert api_download.assets[0].asset_key == 'nfo'
        assert api_download.artifact_size_bytes == 100
        assert session.get(TaskRun,run_id).status == 'SUCCEEDED'
        completed = session.scalar(select(MediaDownloadHistory).where(MediaDownloadHistory.media_download_id == download_id,MediaDownloadHistory.action == 'completed'))
        assert completed.event_metadata['lifecycle']['phase'] == 'complete'
    with pytest.raises(ValueError):
        cancel_operation(operation_id)
    assert not cancel_task_run(run_id,reason='Too late')
    # A callback failure after a committed result cannot revoke or retry it.
    _finalize_execution(prepared=_PreparedExecution(run_id,(operation_id,),{}),runtime_ms=1,worker_result=result,worker_error=RuntimeError('late callback'))
    assert get_operation(operation_id).status == 'SUCCEEDED'


def test_cancellation_wins_before_transactional_completion(library):
    from task_manager.scheduler.executor import ProgressUpdater
    from task_manager.scheduler.operation_control import cancel_task_run
    from task_manager.scheduler.results import TaskResult
    from dailywire_downloader import DownloadCancelled
    factory,(download_id,_) = library
    run_id,_ = start_run(factory,download_id)
    cancel_task_run(run_id,reason='Cancel first')
    with factory() as session, pytest.raises(DownloadCancelled):
        ProgressUpdater(run_id).complete_transactionally(session,TaskResult('Done'))


def test_pipeline_failure_removes_owned_outputs(library,tmp_path,monkeypatch):
    from dailywire_downloader import coordinator
    from dailywire_downloader.storage.publication import PublicationJournal
    from task_manager.tasks import download_adapter
    from backend.db.models.media_download import MediaDownloadBase
    factory,(download_id,_)=library
    def prepare(session,_id,tracker):
        session.rollback()
        return build_download_plan(source=ResolvedDownloadSource('https://media.test/a.mp4','1080p',False,False,'mp4',False),requested_destination=tmp_path/'a.mp4',download_mode='temporary',temporary_root=tmp_path/'temp',assets=(SidecarSpec('nfo','nfo',content=b'<movie/>',extension='nfo'),),attempt_id=tracker.attempt_id)
    def download(_url,path,**kwargs):
        Path(path).write_bytes(b'media');return DownloadResult(path,5)
    monkeypatch.setattr(download_adapter,'prepare_download_plan',prepare)
    monkeypatch.setattr(coordinator,'download_file',download)
    monkeypatch.setattr(PublicationJournal,'publish',lambda *a,**k: (_ for _ in ()).throw(OSError('disk full')))
    with factory() as session,pytest.raises(OSError,match='disk full'):
        download_adapter.run_download(session,media_download_id=download_id)
    assert not (tmp_path/'a.mp4').exists()
    with factory() as session:
        assert session.get(MediaDownloadBase,download_id).artifact_status=='absent'
