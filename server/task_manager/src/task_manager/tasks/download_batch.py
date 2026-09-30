"""Durable download-batch ownership and work estimates, separate from transfers."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import time
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from backend.db import get_session
from backend.db.models.media_download import MediaDownloadBase
from backend.services.media_download_history import record_media_download_history
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from dailywire_downloader import DownloadCancelled
from task_manager.scheduler.db import DownloadBatchItem, TaskOperation, TaskOperationRun, TaskOperationTarget
from task_manager.scheduler.operations import _operation_snapshot
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.operation_context import current_operation_ids
from task_manager.tasks.media_download_operations import (
    cancel_media_download_operation, create_media_download_operation,
    dispatch_queued_media_download_operations, get_active_media_download_operation,
    prepare_media_download_artifact,
)
from task_manager.tasks.workers.download_attempt import serialize_download_attempt

_TERMINAL = {"SUCCEEDED", "FAILED", "PARTIAL", "CANCELED"}


@dataclass(frozen=True)
class BatchTarget:
    id: int
    download_id: int
    title: str
    weight: int
    operation_id: str | None
    owned: bool
    prepared: bool
    error: str | None


def _target(item: DownloadBatchItem) -> BatchTarget:
    return BatchTarget(item.id, item.media_download_id, item.title, item.weight,
                       item.child_operation_id, item.owns_operation, item.prepared, item.error)


def create_batch_manifest(ids: list[int], owner_key: str, run_id: int | None, operation_id: str | None = None, *, previous_owner_key: str | None = None) -> list[BatchTarget]:
    """Freeze the whole selection and byte weights before deleting any file."""
    session = get_session()
    try:
        existing = list(session.scalars(select(DownloadBatchItem).where(DownloadBatchItem.owner_key == owner_key).order_by(DownloadBatchItem.id)))
        if existing:
            return [_target(item) for item in existing]
        previous = list(session.scalars(select(DownloadBatchItem).where(
            DownloadBatchItem.owner_key == previous_owner_key,
        ).order_by(DownloadBatchItem.id))) if previous_owner_key else []
        if previous:
            replacements = []
            for item in previous:
                child = session.get(TaskOperation, item.child_operation_id) if item.child_operation_id else None
                preserve = child is not None and (
                    child.status == "SUCCEEDED"
                    or (not item.owns_operation and child.status not in _TERMINAL)
                )
                replacement = DownloadBatchItem(
                    owner_key=owner_key, owner_run_id=run_id, owner_operation_id=operation_id,
                    media_download_id=item.media_download_id, title=item.title, weight=item.weight,
                    child_operation_id=child.id if preserve else None,
                    owns_operation=item.owns_operation if preserve else False,
                    prepared=preserve, error=None,
                )
                session.add(replacement)
                replacements.append(replacement)
            session.flush()
            targets = [_target(item) for item in replacements]
            session.commit()
            return targets
        downloads = {row.id: row for row in session.scalars(select(MediaDownloadBase).where(MediaDownloadBase.id.in_(ids)))}
        sizes = {
            key: next((int(size) for size in (value.downloaded_bytes, value.artifact_size_bytes) if size is not None and size > 0), None)
            for key, value in downloads.items()
        }
        known = [size for size in sizes.values() if size is not None]
        fallback = max(1, sum(known) // len(known)) if known else 1
        items = []
        for download_id in dict.fromkeys(ids):
            download = downloads.get(download_id)
            item = DownloadBatchItem(
                owner_key=owner_key, owner_run_id=run_id, owner_operation_id=operation_id, media_download_id=download_id,
                title=download.media.title if download else f"Download {download_id}",
                weight=sizes.get(download_id) or fallback,
                prepared=False, owns_operation=False,
                error=None if download else "Media download was removed",
            )
            session.add(item)
            items.append(item)
        session.flush()
        targets = [_target(item) for item in items]
        session.commit()
        return targets
    finally:
        session.close()


def prepare_batch_target(target: BatchTarget, *, force_new: bool, progress=None) -> BatchTarget:
    if target.prepared or target.error:
        return target
    session = get_session()
    try:
        active = get_active_media_download_operation(session, target.download_id)
        active_id = active.id if active else None
        if active is not None and not force_new:
            item = session.get(DownloadBatchItem, target.id)
            item.child_operation_id, item.owns_operation, item.prepared = active.id, False, True
            session.commit()
            return _target(item)
    finally:
        session.close()
    if active_id is not None:
        try:
            cancel_media_download_operation(active_id, reason="Replaced by explicit bulk re-download", acknowledge=True)
        except ValueError:
            # Completion won the cancellation race. Wait for filesystem ownership
            # below and then prepare exactly the requested replacement.
            pass
    # No Session or transaction is retained while a predecessor stops its writers.
    with serialize_download_attempt(target.download_id, progress=progress):
        session = get_session()
        try:
            item = session.get(DownloadBatchItem, target.id)
            if item is None:
                raise DownloadCancelled("Batch owner was removed")
            if item.prepared:
                return _target(item)
            download = session.get(MediaDownloadBase, target.download_id)
            if download is None:
                item.error = "Media download was removed"
                session.commit()
                return _target(item)
            active = get_active_media_download_operation(session, target.download_id)
            if active is not None:
                # Another explicit action may have acquired this artifact while
                # our predecessor was stopping. Observe it; do not claim ownership.
                item.child_operation_id, item.owns_operation, item.prepared = active.id, False, True
            else:
                is_redownload = download.downloaded_at is not None or download.artifact_status in {"available", "missing", "corrupted"}
                record_media_download_history(session, download.id, MediaDownloadHistoryAction.RETRY_REQUESTED, metadata={"source": "SYSTEM", "batch": item.owner_key})
                prepare_media_download_artifact(session, download)
                child = create_media_download_operation(session, download, source="SYSTEM", is_redownload=is_redownload)
                child.context = {**(child.context or {}), "request_priority": "bulk", "batch_owner": item.owner_key}
                item.child_operation_id, item.owns_operation, item.prepared = child.id, True, True
            # Pair child creation and manifest ownership in one transaction. A
            # restarted coordinator must never delete an already replaced output.
            session.flush()
            result = _target(item)
            dispatch_queued_media_download_operations(session)
            session.commit()
            return result
        finally:
            session.close()


def child_completion(operation) -> float:
    """Estimate required work completed; no timer or UI transfer percent is used."""
    if operation is None:
        return 0.0
    if operation.status == "SUCCEEDED":
        return 1.0
    snapshot = (operation.progress_meta or {}).get("download")
    if not isinstance(snapshot, dict):
        return 0.0
    stages = snapshot.get("stages") or ()
    total, done = 0.0, 0.0
    for stage in stages:
        weight = max(0.0, float(stage.get("weight") or 0))
        total += weight
        if stage.get("state") in {"completed", "skipped"}:
            fraction = 1.0
        elif stage.get("state") in {"running", "waiting"} and stage.get("fraction") is not None:
            fraction = max(0.0, min(1.0, float(stage["fraction"])))
        else:
            fraction = 0.0
        done += weight * fraction
    return min(0.99, done / total) if total else 0.0


def _snapshots(targets: list[BatchTarget]):
    ids = [item.operation_id for item in targets if item.operation_id]
    session = get_session()
    try:
        rows = session.scalars(select(TaskOperation).where(TaskOperation.id.in_(ids)).options(
            selectinload(TaskOperation.targets).selectinload(TaskOperationTarget.run_links).selectinload(TaskOperationRun.task_run),
        ))
        return {item.id: _operation_snapshot(item) for item in rows}
    finally:
        session.close()


def cancel_owned_children(targets: list[BatchTarget], *, reason: str) -> None:
    for target in targets:
        if target.owned and target.operation_id:
            try:
                cancel_media_download_operation(target.operation_id, reason=reason, acknowledge=True)
            except ValueError:
                pass


async def run_download_batch(ids: list[int], *, progress=None, force_new: bool = False) -> TaskResult:
    run_id = getattr(progress, "run_id", None)
    operation_id = next(iter(current_operation_ids()), None)
    # Startup recovery may replace a TaskRun. The user operation is the durable
    # owner, so its manifest must outlive an interrupted coordinator attempt.
    generation = 0
    if operation_id:
        with get_session() as session:
            owner = session.get(TaskOperation, operation_id)
            if owner is None:
                raise DownloadCancelled("Batch owner was removed")
            generation = int((owner.context or {}).get("restart_generation", 0))
    owner_key = f"operation:{operation_id}:generation:{generation}" if operation_id else f"run:{run_id}" if run_id is not None else f"adhoc:{uuid4()}"
    previous_owner_key = f"operation:{operation_id}:generation:{generation - 1}" if operation_id and generation else None
    targets = create_batch_manifest(list(dict.fromkeys(ids)), owner_key, run_id, operation_id, previous_owner_key=previous_owner_key)
    # A user restart replaces unfinished owned children. Completed downloads and
    # independently owned active children were preserved in the new manifest.
    force_new = force_new or bool(generation)
    if not targets:
        return TaskResult("No downloads to re-download", {"downloads_requested": 0, "downloads_completed": 0})
    try:
        for index, target in enumerate(targets):
            if progress is not None and callable(progress) and progress():
                raise DownloadCancelled("Bulk re-download was canceled")
            targets[index] = prepare_batch_target(target, force_new=force_new, progress=progress)
        while True:
            if progress is not None and callable(progress) and progress():
                raise DownloadCancelled("Bulk re-download was canceled")
            operations = _snapshots(targets)
            completed, failed, canceled, finishing, active = 0, 0, 0, 0, []
            errors = []
            weighted = 0.0
            for target in targets:
                operation = operations.get(target.operation_id)
                weighted += target.weight * child_completion(operation)
                if target.error or operation is None:
                    failed += 1
                    errors.append(f"{target.title}: {target.error or 'download operation was removed'}")
                elif operation.status == "SUCCEEDED":
                    completed += 1
                elif operation.status in _TERMINAL:
                    canceled += int(operation.status == "CANCELED")
                    failed += int(operation.status != "CANCELED")
                    errors.append(f"{target.title}: {operation.error or operation.message or operation.status}")
                else:
                    active.append(operation)
                    snapshot = (operation.progress_meta or {}).get("download") or {}
                    finishing += int(snapshot.get("phase") == "finishing")
            percentage = min(99, int(100 * weighted / sum(target.weight for target in targets)))
            counts = {"requested": len(targets), "completed": completed, "failed": failed, "canceled": canceled, "finishing": finishing}
            message = f"{completed}/{len(targets)} complete"
            if finishing:
                message += f"; {finishing} finishing"
            if failed or canceled:
                message += f"; {failed} failed; {canceled} canceled"
            if progress is not None:
                progress.set(percentage, message, meta={
                    "batch": {**counts, "estimated": True, "owner_key": owner_key, "child_operation_ids": [target.operation_id for target in targets], "heartbeat_at": time()},
                })
                if hasattr(progress, "set_wait_state"):
                    all_blocked = active and all(item.status in {"WAITING", "QUEUED"} for item in active)
                    waits = [(item.progress_meta or {}).get("wait_state") for item in active]
                    first = next((wait for wait in waits if wait), None)
                    progress.set_wait_state(
                        first["reason"] if all_blocked and first else "download_capacity" if all_blocked else None,
                        first.get("message") if all_blocked and first else "Waiting for downloads" if all_blocked else None,
                    )
            if not active:
                outcome = "partial" if completed and errors else "failed" if errors else "succeeded"
                return TaskResult(
                    f"Re-download finished: {completed}/{len(targets)} complete" + (f"; {len(errors)} unsuccessful" if errors else ""),
                    {"downloads_requested": len(targets), "downloads_completed": completed, "downloads_failed": failed, "downloads_canceled": canceled, "errors": errors},
                    outcome=outcome,
                )
            await asyncio.sleep(0.5)
    except BaseException:
        # Child creation may have committed just before the caller was canceled.
        # Reload durable ownership, rather than relying on a stale local list.
        targets = create_batch_manifest(ids, owner_key, run_id, operation_id)
        cancel_owned_children(targets, reason="Parent bulk operation stopped")
        raise
    finally:
        if run_id is None and operation_id is None:
            session = get_session()
            try:
                session.execute(delete(DownloadBatchItem).where(DownloadBatchItem.owner_key == owner_key))
                session.commit()
            finally:
                session.close()
