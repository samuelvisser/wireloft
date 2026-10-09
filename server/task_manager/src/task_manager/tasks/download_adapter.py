"""Application adapter for the standalone download coordinator.

Workers do not implement download behavior. This adapter translates lifecycle
snapshots into TaskRun reporting and atomically persists successful artifacts.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.media_download import MediaDownloadAsset, MediaDownloadBase
from backend.services.download_plans import prepare_download_plan
from backend.services.media_download_history import (
    download_attempt_metadata, record_media_download_history,
    record_media_download_history_if_exists, record_media_download_operation_history_once,
)
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from config import get_settings
from dailywire_api.pacing import RequestCancelled, request_context
from dailywire_downloader import DownloadCancelled
from dailywire_downloader.capacity import resources
from dailywire_downloader.coordinator import DownloadExecution, execute_download_plan
from dailywire_downloader.storage.identity import inspect_artifact
from dailywire_downloader.storage.replacement import (
    OwnedFile, PreviousDownload, capture_previous_download,
    restore_original_filename, retire_superseded_files,
)
from dailywire_downloader.lifecycle import (
    DownloadSnapshot,
    DownloadTracker,
    download_completion_fraction,
)
from dailywire_downloader.transfer_context import transfer_context
from task_manager.scheduler.operation_context import current_operation_ids
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.media_download_operations import on_media_download_transfer_complete


logger = logging.getLogger(__name__)


class DownloadProgressReporter:
    """Persist one ordered snapshot; numeric TaskRun progress is transfer-only."""
    def __init__(self, progress):
        self.progress = progress
        self.selected_format: str | None = None

    def __call__(self, snapshot: DownloadSnapshot) -> None:
        if self.progress is None:
            return
        media = next((stage for stage in snapshot.stages if stage.id == "media"), None)
        fraction = media.fraction if media is not None else None
        percent = min(99, int(100 * fraction)) if fraction is not None else 0
        main = next(stage for stage in snapshot.stages if stage.id == snapshot.main_activity)
        running = [stage for stage in snapshot.stages if stage.state in ("running", "waiting")]
        # A blocked auxiliary fetch must not pause media that is still moving.
        blocked = bool(running) and all(stage.wait is not None for stage in running)
        wait = asdict(main.wait) if blocked and main.wait else None
        message = main.code.replace("_", " ").capitalize()
        if wait is not None:
            from task_manager.scheduler.executor import request_wait_message
            wait["message"] = request_wait_message(wait["reason"])
            message = wait["message"]
        metadata = {"download": asdict(snapshot), "selected_format": self.selected_format}
        completion_percent = min(99, int(100 * download_completion_fraction(snapshot)))
        # The real executor supports atomic state+wait checkpoints. CLI sinks
        # report the same structured facts without owning a scheduler wait state.
        from task_manager.scheduler.executor import ProgressUpdater
        if isinstance(self.progress, ProgressUpdater):
            from task_manager.scheduler.executor import TaskCancellationRequested
            try:
                self.progress.set(
                    percent,
                    message,
                    meta=metadata,
                    completion_percent=completion_percent,
                    wait_state=wait,
                )
            except TaskCancellationRequested as exc:
                raise DownloadCancelled(str(exc)) from exc
        else:
            self.progress.set(percent, message, meta=metadata)


def _finish_replacement(
    session: Session,
    media_download_id: int,
    previous: PreviousDownload,
    execution: DownloadExecution,
    requested_destination: str,
) -> None:
    """Retire the previous artifact only after the replacement is committed.

    A separate database commit permits restoring the original filename with
    atomic same-directory renames without ever making the only committed
    replacement unavailable if that commit fails.
    """
    new_media = execution.result.path
    new_assets = tuple(asset.path for asset in execution.assets)
    retained = frozenset((new_media, *new_assets))

    normalized = restore_original_filename(
        new_media, new_assets,
        previous=previous, requested_destination=requested_destination,
    )
    if normalized is not None:
        normalized_media, normalized_assets = normalized
        try:
            session.rollback()
            download = session.get(MediaDownloadBase, media_download_id)
            if download is None or download.file_path != new_media:
                raise RuntimeError("Download changed while restoring its original filename")
            identity = inspect_artifact(normalized_media)
            if (identity.size_bytes, identity.fingerprint) != (
                execution.identity.size_bytes, execution.identity.fingerprint
            ):
                raise RuntimeError("Restored media does not match the completed download")
            asset_paths = {
                source.id: target
                for source, target in zip(execution.assets, normalized_assets, strict=True)
            }
            download.file_path = normalized_media
            download.artifact_stat_dev = identity.stat_dev
            download.artifact_stat_ino = identity.stat_ino
            for asset in download.assets:
                path = asset_paths[asset.asset_key]
                new_identity = inspect_artifact(path)
                asset.path = path
                asset.suffix = Path(path).name[len(Path(normalized_media).stem):]
                asset.size_bytes = new_identity.size_bytes
                asset.fingerprint = new_identity.fingerprint
            record_media_download_history(
                session, media_download_id, MediaDownloadHistoryAction.ARTIFACT_RENAMED,
                metadata={"old_path": new_media, "new_path": normalized_media},
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.warning(
                "Replacement is available at '%s', but could not commit the original filename",
                new_media, exc_info=True,
            )
        else:
            # The new artifact remains linked at its original published path
            # until the database's filename change is durable.
            duplicate = PreviousDownload(
                OwnedFile(Path(new_media), execution.identity),
                tuple(OwnedFile(Path(asset.path), asset.identity) for asset in execution.assets),
            )
            retire_superseded_files(
                duplicate, retained_paths=frozenset((normalized_media, *normalized_assets)),
            )
            retained = frozenset((normalized_media, *normalized_assets))

    retire_superseded_files(previous, retained_paths=retained)


def run_download(
    session: Session, *, media_download_id: int, is_redownload: bool = False,
    prepare_existing_artifact: bool = False, progress=None,
) -> TaskResult:
    download = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadCancelled("Media download was deleted before it started")
    title = download.media.title
    publish_status = getattr(download.media, "publish_status", None)
    operation_ids = current_operation_ids()
    run_id = getattr(progress, "run_id", None)
    attempt = {"operation_ids": list(operation_ids)}
    if run_id is not None:
        attempt["task_run_id"] = int(run_id)
    started = datetime.now(timezone.utc)
    record_media_download_history(
        session, media_download_id, MediaDownloadHistoryAction.STARTED,
        metadata={**attempt, "is_redownload": is_redownload, "started_publish_status": publish_status}, occurred_at=started,
    )
    session.commit()
    reporter = DownloadProgressReporter(progress)
    tracker = DownloadTracker(reporter, progress if callable(progress) else None)
    execution = None
    previous: PreviousDownload | None = None
    preserving_artifact = False
    committed = False
    resources.media.configure(get_settings().download_settings.max_concurrent_downloads)
    try:
        with tracker:
            if prepare_existing_artifact or download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
                tracker.ensure_active()
                tracker.preparing("prepare_existing_artifact")
                current = session.get(MediaDownloadBase, media_download_id)
                if current is None:
                    raise DownloadCancelled("Media download was deleted before replacement preparation")
                preserving_artifact = (
                    current.artifact_status != MediaDownloadArtifactStatus.ABSENT.value
                )
                if preserving_artifact:
                    previous = capture_previous_download(
                        current.file_path,
                        size_bytes=current.artifact_size_bytes,
                        fingerprint=current.artifact_fingerprint,
                        assets=tuple(
                            (asset.path, asset.size_bytes, asset.fingerprint)
                            for asset in current.assets
                        ),
                    )
                # An attempt owns none of the previous output paths until a new
                # artifact is committed. Never delete or reset the old artifact
                # merely because retry work is starting, including Missing or
                # Corrupted records that may still have a physical file.
                current.automatic_retry_suppressed = False
                session.commit()
                session.expire_all()

            def waiting(event):
                tracker.wait("prepare", event.reason if event else None, event.until if event else None)
            with request_context(observer=waiting, should_cancel=tracker.is_canceled), transfer_context(tracker.is_canceled, waiting):
                plan = prepare_download_plan(session, media_download_id, tracker)
            reporter.selected_format = plan.source.format_downloaded

            def reserved(destination: str) -> None:
                current = session.get(MediaDownloadBase, media_download_id)
                if current is None:
                    raise DownloadCancelled("Download was deleted before reserving its destination")
                if not preserving_artifact:
                    current.file_path = destination
                    session.commit()

            execution = execute_download_plan(
                plan, tracker=tracker, resources=resources,
                on_destination_reserved=reserved,
                on_media_transfer_complete=on_media_download_transfer_complete,
            )
            tracker.ensure_active()
            # Stop concurrent reporting before entering the final transaction;
            # no auxiliary thread owns a Session or writes past publication.
            lifecycle = tracker.finish()
            session.rollback()
            session.expire_all()
            download = session.get(MediaDownloadBase, media_download_id)
            if download is None:
                raise DownloadCancelled("Download was deleted during execution")
            from task_manager.scheduler.executor import ProgressUpdater
            identity = execution.identity
            download.file_path = execution.result.path
            download.assets.clear()
            session.flush()
            for asset in execution.assets:
                suffix = Path(asset.path).name[len(Path(execution.result.path).stem):]
                download.assets.append(MediaDownloadAsset(
                    asset_key=asset.id, kind=asset.kind, path=asset.path, suffix=suffix,
                    size_bytes=asset.identity.size_bytes, fingerprint=asset.identity.fingerprint,
                ))
            download.artifact_stat_dev, download.artifact_stat_ino = identity.stat_dev, identity.stat_ino
            download.artifact_size_bytes, download.artifact_fingerprint = identity.size_bytes, identity.fingerprint
            download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
            download.artifact_error = None
            download.automatic_retry_suppressed = False
            download.downloaded_bytes = execution.result.bytes_downloaded
            download.format_downloaded = execution.format_downloaded
            finished = datetime.now(timezone.utc)
            download.downloaded_at = finished
            if isinstance(download.media, Episode):
                download.downloaded_publish_status = publish_status
            result_data = {
                "media_download_id": media_download_id, "is_redownload": is_redownload,
                "file_path": execution.result.path, "downloaded_bytes": execution.result.bytes_downloaded,
                "format_downloaded": execution.format_downloaded,
                "thumbnail_path": download.thumbnail_path, "nfo_path": download.nfo_path,
                "lifecycle": asdict(lifecycle),
            }
            record_media_download_history(
                session, media_download_id, MediaDownloadHistoryAction.COMPLETED,
                metadata=download_attempt_metadata(
                    started_at=started, finished_at=finished, **attempt, **result_data,
                    started_publish_status=publish_status, downloaded_publish_status=publish_status,
                ), occurred_at=finished,
            )
            result = TaskResult(summary=f"Downloaded {title}", data=result_data)
            if isinstance(progress, ProgressUpdater):
                progress.complete_transactionally(session, result)
            session.commit()
            committed = True
            if previous is not None:
                # The new artifact and task result are already committed. A
                # failed post-commit filename cleanup must not turn a successful
                # download into a failed TaskRun or revoke its replacement.
                try:
                    _finish_replacement(
                        session, media_download_id, previous, execution,
                        plan.requested_destination,
                    )
                except Exception:
                    session.rollback()
                    logger.exception(
                        "Replacement was committed, but old-file cleanup failed for download %s",
                        media_download_id,
                    )
        return result
    except BaseException as exc:
        tracker.cancel(user_requested=isinstance(exc, (DownloadCancelled, RequestCancelled)))
        tracker.stop_reporting()
        session.rollback()
        if execution is not None and not committed:
            execution.rollback()
        if not isinstance(exc, Exception):
            raise
        finished = datetime.now(timezone.utc)
        metadata = download_attempt_metadata(
            started_at=started, finished_at=finished, is_redownload=is_redownload,
            **attempt, error=exc, lifecycle=asdict(tracker.snapshot()),
        )
        if isinstance(exc, (DownloadCancelled, RequestCancelled)):
            entry = record_media_download_operation_history_once(
                session, media_download_id, MediaDownloadHistoryAction.CANCELLED,
                operation_ids=operation_ids, metadata=metadata, occurred_at=finished,
            )
        else:
            entry = record_media_download_history_if_exists(
                session, media_download_id, MediaDownloadHistoryAction.FAILED,
                metadata=metadata, occurred_at=finished,
            )
        if entry is not None:
            session.commit()
        raise
    finally:
        if execution is not None:
            execution.cleanup_workspace()
