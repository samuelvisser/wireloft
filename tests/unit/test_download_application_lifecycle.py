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
        for key in ('download_episode', 'download_movie', 'batch_test'):
            session.add(TaskDefinition(key=key, title=key, allowed_resource_types=['media_download'], default_max_retries=0))
        first = _make_download(session, slug='main')
        second = _make_download(session, slug='extra')
        first.downloaded_bytes, second.downloaded_bytes = 900, 100
        first.media.description = second.media.description = 'Description'
        session.commit()
        ids = (first.id, second.id)
    from task_manager.tasks import download_batch, download_adapter
    monkeypatch.setattr(download_batch, 'dispatch_queued_media_download_operations', lambda _: 0)
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
        assert MediaDownloadAPIRead.model_validate(record).assets[0].asset_key == 'nfo'
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


def test_batch_manifest_weights_survive_new_coordinator_run(library):
    from task_manager.tasks.download_batch import create_batch_manifest,prepare_batch_target
    from task_manager.scheduler.db import TaskOperation,TaskRun,TaskDefinition
    from task_manager.scheduler.types import ResourceType,TaskStatus
    from backend.db.models.media_download import MediaDownloadBase
    factory,ids = library
    with factory() as session:
        owner = TaskOperation(id='batch-owner',kind='media.bulk_retry',source='UI',resource_type='media_download',resource_id=None,title='Batch',status='RUNNING',progress=0)
        session.add(owner)
        definition = session.scalar(select(TaskDefinition).where(TaskDefinition.key == 'batch_test'))
        run = TaskRun(definition_id=definition.id,resource_type=ResourceType.MEDIA_DOWNLOAD,resource_id=ids[0],status=TaskStatus.RUNNING,progress=0,attempt_count=1,max_retries=0)
        session.add(run);session.commit();run_id=run.id
    first = create_batch_manifest(list(ids),'operation:batch-owner',run_id,'batch-owner')
    assert [target.weight for target in first] == [900,100]
    child = prepare_batch_target(first[0],force_new=True)
    assert child.owned and child.prepared
    with factory() as session:
        operation = session.get(TaskOperation,child.operation_id)
        operation.status='SUCCEEDED'
        session.get(MediaDownloadBase,ids[0]).downloaded_bytes=5000
        session.commit()
    recovered = create_batch_manifest([ids[0]],'operation:batch-owner',run_id+100,'batch-owner')
    assert len(recovered)==2 and recovered[0].weight==900
    assert prepare_batch_target(recovered[0],force_new=True).operation_id == child.operation_id


def test_bulk_does_not_cancel_reused_independent_download(library,monkeypatch):
    from task_manager.tasks import download_batch
    from task_manager.tasks.media_download_operations import create_media_download_operation
    from backend.db.models.media_download import MediaDownloadBase
    factory,ids=library
    with factory() as session:
        operation=create_media_download_operation(session,session.get(MediaDownloadBase,ids[0]),source='UI')
        session.commit();operation_id=operation.id
    target=download_batch.create_batch_manifest([ids[0]],'adhoc:test',None)[0]
    target=download_batch.prepare_batch_target(target,force_new=False)
    assert target.operation_id==operation_id and not target.owned
    calls=[]
    monkeypatch.setattr(download_batch,'cancel_media_download_operation',lambda *a,**k:calls.append(a))
    download_batch.cancel_owned_children([target],reason='Parent canceled')
    assert calls==[]


def test_bulk_uses_stage_work_not_individual_transfer_percentage(tmp_path):
    from task_manager.tasks.download_batch import child_completion
    tracker=DownloadTracker()
    plan=build_download_plan(source=ResolvedDownloadSource('https://media.test/a.mp4','1080p',False,False,'mp4',False),requested_destination=tmp_path/'a.mp4',download_mode='direct',temporary_root=tmp_path/'tmp',metadata_tags=(('title','a'),),attempt_id=tracker.attempt_id)
    tracker.install(plan);tracker.start('media');tracker.progress('media',DownloadProgress(100,100));tracker.complete('media');tracker.start('embed')
    operation=SimpleNamespace(status='RUNNING',progress=99,progress_meta={'download':asdict(tracker.snapshot())})
    assert .4<child_completion(operation)<.6
    tracker.complete('embed')
    operation.progress_meta={'download':asdict(tracker.snapshot())}
    assert .9<child_completion(operation)<1
    operation.status='SUCCEEDED'
    assert child_completion(operation)==1


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


def test_batch_estimates_size_weighted_work_and_reports_partial_outcome(library, tmp_path, monkeypatch):
    from task_manager.tasks import download_batch
    from dataclasses import replace
    factory, ids = library
    tracker = DownloadTracker()
    tracker.install(build_download_plan(source=ResolvedDownloadSource('https://media.test/a.mp4','1080p',False,False,'mp4',False), requested_destination=tmp_path/'movie.mp4', download_mode='direct', temporary_root=tmp_path/'temp', metadata_tags=(('title','Movie'),), attempt_id=tracker.attempt_id))
    tracker.start('media'); tracker.progress('media', DownloadProgress(100,100)); tracker.complete('media'); tracker.start('embed')
    movie = SimpleNamespace(status='RUNNING', progress=99, progress_meta={'download':asdict(tracker.snapshot())}, error=None, message='Embedding')
    extra = SimpleNamespace(status='SUCCEEDED', progress=100, progress_meta=None, error=None, message=None)
    seen = []
    class Progress:
        def __call__(self): return False
        def set(self, percent, message=None, meta=None): seen.append((percent, meta))
        def set_wait_state(self, *args): pass
    monkeypatch.setattr(download_batch, 'prepare_batch_target', lambda target, **_: replace(target, operation_id=str(target.download_id), prepared=True))
    reads = []
    def snapshots(_targets):
        if reads:
            movie.status='FAILED';movie.error='Embedding failed'
        reads.append(1)
        return {str(ids[0]):movie, str(ids[1]):extra}
    monkeypatch.setattr(download_batch, '_snapshots', snapshots)
    result = asyncio.run(download_batch.run_download_batch(list(ids), progress=Progress()))
    assert 50 <= seen[0][0] <= 60
    assert seen[0][1]['batch']['finishing'] == 1
    assert result.outcome == 'partial'
    assert result.data['downloads_completed'] == 1
    assert result.data['downloads_failed'] == 1


def test_explicit_batch_restart_keeps_completed_children_but_replaces_failures(library):
    from task_manager.tasks import download_batch
    from task_manager.scheduler.db import TaskOperation
    factory, ids = library
    with factory() as session:
        session.add(TaskOperation(id='restart-owner',kind='media.bulk_retry',source='UI',resource_type='show',resource_id=1,title='Batch',status='PARTIAL',progress=100))
        session.commit()
    first = download_batch.create_batch_manifest(list(ids), 'operation:restart-owner:generation:0', None, 'restart-owner')
    first = [download_batch.prepare_batch_target(target, force_new=False) for target in first]
    with factory() as session:
        session.get(TaskOperation, first[0].operation_id).status='SUCCEEDED'
        session.get(TaskOperation, first[1].operation_id).status='FAILED'
        session.commit()
    restarted = download_batch.create_batch_manifest(list(ids), 'operation:restart-owner:generation:1', None, 'restart-owner', previous_owner_key='operation:restart-owner:generation:0')
    assert restarted[0].prepared and restarted[0].operation_id == first[0].operation_id
    assert not restarted[1].prepared and restarted[1].operation_id is None
    assert [target.weight for target in restarted] == [900,100]
    assert download_batch.prepare_batch_target(restarted[0],force_new=True).operation_id == first[0].operation_id
    replacement=download_batch.prepare_batch_target(restarted[1],force_new=True)
    assert replacement.operation_id != first[1].operation_id
    # An old coordinator's cancellation still addresses only its own manifest.
    assert first[1].operation_id != replacement.operation_id
