from __future__ import annotations

from contextlib import contextmanager
import os

from sqlalchemy.orm import Session

from backend.db import get_session
from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.services.episode_download_delay import (
    episode_download_delay_passed,
    episode_download_delay_ready_at,
)
from backend.services.media_download_history import record_media_download_history
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import (
    cancel_media_download_operation,
    create_media_download_operation,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    is_media_download_publication_delay_wait,
    prepare_media_download_artifact,
)
from task_manager.tasks.workers.download_attempt import serialize_download_attempt
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


class DownloadActionError(ValueError):
    def __init__(self, kind: str, detail: str):
        self.kind = kind
        super().__init__(detail)


@contextmanager
def db_session():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def retry_media_download(session: Session, media_download_id: int) -> MediaDownloadBase:
    download = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadActionError("missing", "Media download not found")
    if get_active_media_download_operation(session, media_download_id) is not None:
        raise DownloadActionError("conflict", "This download already has an active operation")
    prepare_media_download_artifact(session, download)
    session.flush()
    return download


def retry_media_download_action(
        media_download_id: int,
        *,
        source: str = OperationSource.UI,
        reuse_matching_active: bool = False,
        redownload_when_delay_passed: bool = False,
        schedule_for_delay: bool = False,
) -> str:
    """Replace one download attempt and return the new media.download operation ID."""
    active_operation_id: str | None = None
    is_redownload = False
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            raise DownloadActionError("missing", "Media download not found")

        active = get_active_media_download_operation(s, media_download_id)
        if schedule_for_delay and is_media_download_publication_delay_wait(active):
            return str(active.id)

        if isinstance(download, EpisodeMediaDownload):
            episode = s.get(Episode, download.media_item_id)
            download.redownload_when_delay_passed = bool(
                redownload_when_delay_passed
                and not schedule_for_delay
                and episode is not None
                and episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL
                and not episode_download_delay_passed(episode)
            )

        record_media_download_history(
            s,
            media_download_id,
            MediaDownloadHistoryAction.RETRY_REQUESTED,
            metadata={"source": source},
        )
        s.commit()
        active = get_active_media_download_operation(s, media_download_id)
        if active is not None:
            if reuse_matching_active and active.source == source:
                return str(active.id)
            active_operation_id = str(active.id)
        is_redownload = (
            download.downloaded_at is not None
            or download.artifact_status in {"available", "missing", "corrupted"}
        )

    if active_operation_id is not None:
        cancel_media_download_operation(
            active_operation_id,
            reason="Replaced by retry",
            acknowledge=True,
        )

    with db_session() as s:
        try:
            download = s.get(MediaDownloadBase, media_download_id)
            if download is None:
                raise DownloadActionError("missing", "Media download not found")
            scheduled_ready_at = None
            operation_source = source
            if schedule_for_delay and isinstance(download, EpisodeMediaDownload):
                episode = s.get(Episode, download.media_item_id)
                if episode is not None:
                    scheduled_ready_at = episode_download_delay_ready_at(episode)
                operation_source = OperationSource.SYSTEM.value

            operation = create_media_download_operation(
                s,
                download,
                source=operation_source,
                is_redownload=is_redownload,
                prepare_existing_artifact=True,
                not_before=scheduled_ready_at,
            )
            dispatch_queued_media_download_operations(s)
            operation_id = str(operation.id)
            s.commit()
            return operation_id
        except Exception:
            s.rollback()
            raise


def cancel_media_download_action(
        media_download_id: int,
        *,
        allow_inactive: bool = False,
        missing_ok: bool = False,
) -> MediaDownloadBase | None:
    """Cancel one download and durably suppress automatic replacement work."""
    operation_id: str | None = None
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            if missing_ok:
                return None
            raise DownloadActionError("missing", "Media download not found")
        operation = get_active_media_download_operation(s, media_download_id)
        if operation is None:
            if not allow_inactive:
                raise DownloadActionError("conflict", "This download is not currently in progress")
        else:
            operation_id = str(operation.id)

    if operation_id is not None:
        try:
            cancel_media_download_operation(operation_id, reason="Canceled by user", acknowledge=True)
        except ValueError as exc:
            if not allow_inactive:
                raise DownloadActionError("conflict", "This download is not currently in progress") from exc

    with db_session() as s:
        try:
            download = s.get(MediaDownloadBase, media_download_id)
            if download is None:
                if missing_ok:
                    return None
                raise DownloadActionError("missing", "Media download not found")

            # Persist the user's intent even when an earlier bulk attempt already
            # canceled the active worker but crashed before recording suppression.
            download.automatic_retry_suppressed = (
                download.artifact_status != MediaDownloadArtifactStatus.AVAILABLE.value
            )
            if isinstance(download, EpisodeMediaDownload):
                download.redownload_when_final = False
                download.redownload_when_delay_passed = False
            s.commit()
            s.refresh(download)
            _ = download.assets
            s.expunge(download)
            payload = download
        except Exception:
            s.rollback()
            raise

    # Close the cancellation/requeue race without canceling a newer explicit retry.
    with db_session() as s:
        replacement = get_active_media_download_operation(s, media_download_id)
        replacement_id = (
            replacement.id
            if replacement is not None and replacement.source == OperationSource.SYSTEM.value
            else None
        )

    if replacement_id is not None:
        try:
            cancel_media_download_operation(replacement_id, reason="Canceled by user", acknowledge=True)
        except ValueError:
            pass

    return payload


_DELETABLE_MEDIA_DOWNLOAD_ARTIFACT_STATUSES = {
    MediaDownloadArtifactStatus.ABSENT.value,
    MediaDownloadArtifactStatus.MISSING.value,
}


def delete_unavailable_media_download(
        session: Session,
        media_download_id: int,
) -> None:
    """Delete a MediaDownload row only when no managed artifact is available."""
    download = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadActionError("missing", "Media download not found")
    if get_active_media_download_operation(session, media_download_id) is not None:
        raise DownloadActionError("conflict", "This download already has an active operation")
    if download.artifact_status not in _DELETABLE_MEDIA_DOWNLOAD_ARTIFACT_STATUSES:
        raise DownloadActionError(
            "conflict",
            "Only downloads without an available artifact can be deleted",
        )

    # Refuse destructive changes when the filesystem cannot be checked. This is
    # especially important for container mounts: an unavailable mount must not
    # make an existing artifact look safely deletable.
    try:
        os.stat(download.file_path)
    except FileNotFoundError:
        recorded_path_exists = False
    except OSError as exc:
        raise DownloadActionError(
            "conflict",
            f"Could not verify that the download artifact is absent: {exc}",
        ) from exc
    else:
        recorded_path_exists = True

    if download.artifact_status == MediaDownloadArtifactStatus.MISSING.value:
        # Reconcile immediately before deleting so a restored file or a
        # same-directory rename wins over stale Missing state from the page.
        current_path = resolve_media_download_file(session, download)
        if (
            recorded_path_exists
            or current_path is not None
            or download.artifact_status not in _DELETABLE_MEDIA_DOWNLOAD_ARTIFACT_STATUSES
        ):
            raise DownloadActionError(
                "conflict",
                "The download has an available artifact and cannot be deleted",
            )
    elif recorded_path_exists:
        # ABSENT rows are intentionally outside the FileWatcher reconciliation
        # set. A physical file at the planned output path still makes the record
        # non-deletable even if the database says Not downloaded.
        raise DownloadActionError(
            "conflict",
            "The download has an available artifact and cannot be deleted",
        )

    session.delete(download)
    session.flush()


def delete_unavailable_media_download_action(
        media_download_id: int,
        *,
        missing_ok: bool = False,
) -> bool:
    """Delete one confirmed-unavailable MediaDownload row as a serialized user action."""
    with serialize_download_attempt(media_download_id), db_session() as s:
        try:
            if s.get(MediaDownloadBase, media_download_id) is None:
                if missing_ok:
                    return False
                raise DownloadActionError("missing", "Media download not found")

            delete_unavailable_media_download(s, media_download_id)
            s.commit()
            return True
        except DownloadActionError:
            # A Missing-row recheck may have restored the artifact state or
            # discovered a same-directory rename. Persist that reconciliation
            # even though the destructive action itself is rejected.
            s.commit()
            raise
        except Exception:
            s.rollback()
            raise


def delete_media_download_artifact_action(
        media_download_id: int,
        *,
        missing_ok: bool = False,
) -> bool:
    """Cancel active work and remove one managed artifact without deleting its MediaDownload row."""
    cancel_media_download_action(
        media_download_id,
        allow_inactive=True,
        missing_ok=missing_ok,
    )

    with serialize_download_attempt(media_download_id), db_session() as s:
        try:
            download = s.get(MediaDownloadBase, media_download_id)
            if download is None:
                if missing_ok:
                    return False
                raise DownloadActionError("missing", "Media download not found")

            prepare_media_download_artifact(s, download)
            # A profile-wide delete is explicit user intent. Keep automatic
            # reconciliation from immediately replacing this artifact even if a
            # stale worker or profile sweep observes the row before its parent
            # Download Profile disable becomes visible.
            download.automatic_retry_suppressed = True
            s.commit()
            return True
        except Exception:
            s.rollback()
            raise
