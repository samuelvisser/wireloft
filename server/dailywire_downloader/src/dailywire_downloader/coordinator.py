"""Execute an immutable plan. No ORM, HTTP API models, settings or scheduler."""
from __future__ import annotations

import errno
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .capacity import DownloadResources, resources as default_resources
from .downloader import download_file, download_hls
from .errors import DownloadCancelled, DownloadError
from .ffmpeg import embed_media, remux_to_mp4
from .hls_bundle import download_hls_bundle, hls_asset_marker, hls_asset_root, missing_hls_bundle_files
from .lifecycle import DownloadTracker
from .models import DownloadProgress, DownloadResult
from .plan import DownloadPlan
from .sidecars import AcquiredSidecar, SidecarDownloads
from .storage import TemporaryDownloadWorkspace, create_temporary_download_workspace, publish_temporary_download, reserve_unique_download_path
from .storage.artifacts import remove_download_artifacts
from .storage.copying import copy_file
from .storage.identity import ArtifactIdentity, inspect_artifact
from .storage.publication import PublicationJournal


@dataclass(frozen=True)
class PublishedSidecar:
    id: str
    kind: str
    path: str
    identity: ArtifactIdentity


@dataclass
class DownloadExecution:
    result: DownloadResult
    format_downloaded: str
    identity: ArtifactIdentity
    assets: tuple[PublishedSidecar, ...]
    workspace: TemporaryDownloadWorkspace
    journal: PublicationJournal
    preserve_workspace: bool = False

    def rollback(self) -> None:
        try:
            self.journal.rollback()
            try:
                current = inspect_artifact(self.result.path)
            except FileNotFoundError:
                return
            if current == self.identity:
                remove_download_artifacts(self.result.path)
        except OSError:
            # Preserve the crash-recovery journal if any rollback I/O fails.
            self.preserve_workspace = True
            raise

    def cleanup_workspace(self) -> None:
        if not self.preserve_workspace:
            self.workspace.cleanup()


@contextmanager
def _local_activity(tracker: DownloadTracker, resources: DownloadResources, activity: str) -> Iterator[None]:
    with tracker.activity(activity, deadline_seconds=3600):
        with resources.processing.acquire(
            should_cancel=tracker.is_canceled,
            waiting=lambda value: tracker.wait(activity, "processing_capacity" if value else None),
        ):
            yield


def _tree_size(root: Path) -> int:
    files = list(root.rglob("*"))
    if any(path.is_symlink() for path in files):
        raise DownloadError("HLS assets must not contain symbolic links")
    return sum(path.stat().st_size for path in files if path.is_file())


def _publish_hls_assets(
    source: Path, destination: Path, *, tracker: DownloadTracker, transferred: int, total: int,
) -> None:
    if not source.is_dir():
        raise DownloadError("Completed HLS download is missing its media assets")
    if destination.exists():
        raise FileExistsError(destination)
    try:
        from .storage.temporary import _publish_complete_file
        _publish_complete_file(source, destination)
        tracker.progress("publish", DownloadProgress(total, total))
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    copied = transferred
    def copy_one(src: str, dst: str) -> str:
        nonlocal copied
        amount = copy_file(
            Path(src), Path(dst), should_cancel=tracker.is_canceled,
            progress=lambda value: tracker.progress("publish", DownloadProgress(copied + value.bytes_downloaded, total)),
        )
        copied += amount
        return dst
    try:
        shutil.copytree(source, destination, copy_function=copy_one)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    shutil.rmtree(source)


def execute_download_plan(
    plan: DownloadPlan, *, tracker: DownloadTracker,
    resources: DownloadResources = default_resources,
    on_destination_reserved: Callable[[str], None] | None = None,
    on_media_transfer_complete: Callable[[], None] | None = None,
) -> DownloadExecution:
    """Keep all optional behavior, resource ownership and publication here.

    Returned artifacts are complete but not yet committed to the application.
    The caller commits domain state, then releases the recovery workspace. A
    failed database commit must call rollback before cleanup_workspace.
    """
    tracker.install(plan)
    workspace = create_temporary_download_workspace(plan.temporary_root, plan.requested_destination)
    reservation = None
    assets = None
    destination: Path | None = None
    journal: PublicationJournal | None = None
    published: list[PublishedSidecar] = []
    successful = False
    owned_media: ArtifactIdentity | None = None
    transfer_path: Path | None = None
    try:
        if plan.download_mode == "direct":
            reservation = reserve_unique_download_path(plan.requested_destination)
            media_path = reservation.path
            destination = media_path
            if on_destination_reserved is not None:
                on_destination_reserved(str(media_path))
        else:
            media_path = workspace.path
        assets = SidecarDownloads(plan.assets, workspace.workspace, tracker, resources)
        transfer_path = Path(str(media_path) + ".rawts") if plan.source.remux_to_mp4 else media_path
        with tracker.activity("media"):
            with resources.media.acquire(
                should_cancel=tracker.is_canceled,
                waiting=lambda value: tracker.wait("media", "download_capacity" if value else None),
            ):
                transfer = download_hls_bundle if plan.source.hls_bundle else download_hls if plan.source.use_hls else download_file
                result = transfer(
                    plan.source.url, str(transfer_path),
                    progress=lambda value: tracker.progress("media", value), should_cancel=tracker.is_canceled,
                )
        if media_path.is_file() and not plan.source.remux_to_mp4:
            owned_media = inspect_artifact(media_path)
        # Completion of the transfer releases its lease, not the operation. The
        # adapter can dispatch the next queued media after the snapshot commits.
        if on_media_transfer_complete is not None:
            on_media_transfer_complete()

        if plan.source.remux_to_mp4:
            with _local_activity(tracker, resources, "remux"):
                remux_to_mp4(str(transfer_path), str(media_path), ffmpeg_path=plan.ffmpeg_path, should_cancel=tracker.is_canceled)
            transfer_path.unlink(missing_ok=True)
            owned_media = inspect_artifact(media_path)
        if plan.metadata_tags or plan.artwork_asset_id is not None:
            artwork = assets.get(plan.artwork_asset_id) if plan.artwork_asset_id is not None else None
            with _local_activity(tracker, resources, "embed"):
                embed_media(
                    str(media_path), metadata=dict(plan.metadata_tags),
                    thumbnail_path=str(artwork.path) if artwork is not None else None,
                    audio_only=plan.source.audio_only, ffmpeg_path=plan.ffmpeg_path,
                    should_cancel=tracker.is_canceled,
                )
            owned_media = inspect_artifact(media_path)
        acquired: list[AcquiredSidecar] = []
        for spec in plan.assets:
            asset = assets.get(spec.id)
            if asset is not None:
                acquired.append(asset)
            elif spec.publish:
                tracker.skip(f"publish:{spec.id}", f"Optional {spec.kind} was not published")
        targets = [item.target_suffix for item in acquired if item.spec.publish]
        if len(set(targets)) != len(targets) or media_path.suffix in targets:
            raise DownloadError("Auxiliary assets would collide with another planned output")

        with _local_activity(tracker, resources, "publish"):
            if plan.download_mode == "temporary":
                media_size = media_path.stat().st_size
                total = media_size + (_tree_size(hls_asset_root(media_path)) if plan.source.hls_bundle else 0)
                destination = publish_temporary_download(
                    media_path, plan.requested_destination, should_cancel=tracker.is_canceled,
                    progress=lambda value: tracker.progress("publish", DownloadProgress(value.bytes_downloaded, total)),
                )
                # Record ownership before any subsequent HLS publication can
                # fail, including when the main file crossed filesystems.
                owned_media = inspect_artifact(destination)
                if plan.source.hls_bundle:
                    _publish_hls_assets(hls_asset_root(media_path), hls_asset_root(destination), tracker=tracker, transferred=media_size, total=total)
            assert destination is not None
            owned_media = inspect_artifact(destination)
            journal = PublicationJournal(workspace.workspace, destination)
        for asset in acquired:
            if not asset.spec.publish:
                continue
            activity = f"publish:{asset.spec.id}"
            with tracker.activity(activity, deadline_seconds=1800):
                path = journal.publish(
                    asset.path, asset.target_suffix, should_cancel=tracker.is_canceled,
                    progress=lambda value, activity=activity: tracker.progress(activity, value),
                )
                published.append(PublishedSidecar(asset.spec.id, asset.spec.kind, str(path), inspect_artifact(path)))
        with tracker.activity("verify", deadline_seconds=120):
            identity = inspect_artifact(destination)
            if identity.size_bytes <= 0:
                raise DownloadError("Downloaded media is empty")
            if plan.source.hls_bundle and missing_hls_bundle_files(destination):
                raise DownloadError("Published HLS bundle is incomplete")
        tracker.start("finalize", deadline_seconds=120)
        tracker.ensure_active()
        successful = True
        return DownloadExecution(
            DownloadResult(str(destination), result.bytes_downloaded, result.segments_downloaded),
            plan.source.format_downloaded, identity, tuple(published), workspace, journal,
        )
    except BaseException as exc:
        tracker.cancel(user_requested=isinstance(exc, DownloadCancelled) and tracker.failure is None)
        if tracker.failure is not None and tracker.failure is not exc:
            raise tracker.failure from exc
        raise
    finally:
        # No worker can write into a workspace after it is removed, even when a
        # future failed or cancellation arrived during an unrelated media stage.
        if assets is not None:
            assets.close()
        if not successful:
            if journal is not None:
                journal.rollback()
            if destination is not None and owned_media is not None:
                try:
                    current = inspect_artifact(destination)
                except FileNotFoundError:
                    current = None
                if current == owned_media:
                    remove_download_artifacts(str(destination))
            if transfer_path is not None and plan.source.remux_to_mp4:
                transfer_path.unlink(missing_ok=True)
            workspace.cleanup()
        if reservation is not None:
            reservation.release_if_unclaimed()
