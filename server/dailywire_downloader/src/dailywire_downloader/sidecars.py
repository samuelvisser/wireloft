"""Concurrent auxiliary acquisition, independent of media type and destination."""
from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from pathlib import Path

from .capacity import DownloadResources
from .errors import DownloadCancelled, DownloadError, MediaUnavailableError
from .http import http_get, wait_for_retry
from .lifecycle import DownloadTracker
from .models import DownloadProgress, _extension_for_direct_file
from .plan import SidecarSpec

_CHUNK_SIZE = 256 * 1024


@dataclass(frozen=True)
class AcquiredSidecar:
    spec: SidecarSpec
    path: Path
    target_suffix: str
    size_bytes: int


class InvalidSidecar(DownloadError):
    """An asset fails its planned format or size contract; retries cannot fix it."""


def acquire_sidecar(spec: SidecarSpec, workspace: Path, tracker: DownloadTracker, resources: DownloadResources) -> AcquiredSidecar:
    activity = f"acquire:{spec.id}"
    with tracker.activity(activity, foreground=False):
        for attempt in range(spec.attempts):
            tracker.ensure_active()
            path: Path | None = None
            try:
                with resources.sidecars.acquire(
                    should_cancel=tracker.is_canceled,
                    waiting=lambda value: tracker.wait(activity, "sidecar_capacity" if value else None),
                ):
                    if spec.content is not None:
                        path = workspace / f"{spec.id}.{spec.extension}"
                        with path.open("xb") as out:
                            out.write(spec.content)
                            out.flush()
                            os.fsync(out.fileno())
                        return AcquiredSidecar(spec, path, spec.target_suffix or f".{spec.extension}", len(spec.content))
                    assert spec.url is not None
                    with http_get(spec.url, retries=0) as response:
                        extension = _extension_for_direct_file(spec.url, response.headers.get("Content-Type"))
                        if extension == "bin":
                            extension = spec.extension
                        if spec.allowed_extensions and extension not in spec.allowed_extensions:
                            raise InvalidSidecar(f"Unsupported format for {spec.kind}: {extension}")
                        raw_length = response.headers.get("Content-Length")
                        total = int(raw_length) if raw_length and raw_length.isdigit() else None
                        if total is not None and total > spec.maximum_bytes:
                            raise InvalidSidecar(f"{spec.kind} exceeds its size limit")
                        path = workspace / f"{spec.id}.{extension}"
                        received = 0
                        with path.open("xb") as out:
                            for chunk in response.iter_chunks(_CHUNK_SIZE):
                                tracker.ensure_active()
                                received += len(chunk)
                                if received > spec.maximum_bytes:
                                    raise InvalidSidecar(f"{spec.kind} exceeds its size limit")
                                out.write(chunk)
                                tracker.progress(activity, DownloadProgress(received, total))
                            out.flush()
                            os.fsync(out.fileno())
                        if received == 0 or (total is not None and received != total):
                            raise DownloadError(f"Incomplete {spec.kind} download")
                        return AcquiredSidecar(spec, path, spec.target_suffix or f".{extension}", received)
            except BaseException as exc:
                if path is not None:
                    path.unlink(missing_ok=True)
                if isinstance(exc, (DownloadCancelled, InvalidSidecar, MediaUnavailableError)) or not isinstance(exc, Exception):
                    raise
                if attempt + 1 == spec.attempts:
                    raise
                # Release the network lease before waiting. Retry just this asset,
                # never the media transfer that is running alongside it.
                wait_for_retry(exc, attempt)
    raise RuntimeError("Sidecar acquisition exhausted without a result")


class SidecarDownloads:
    """Own every future until it stops; cleanup cannot race an abandoned writer."""
    def __init__(self, assets: tuple[SidecarSpec, ...], workspace: Path, tracker: DownloadTracker, resources: DownloadResources):
        self._tracker = tracker
        self._executor = ThreadPoolExecutor(max_workers=max(1, min(4, len(assets))), thread_name_prefix="download-asset")
        self._futures: dict[str, Future[AcquiredSidecar]] = {}
        self._resolved: dict[str, AcquiredSidecar | None] = {}
        self._specs = {asset.id: asset for asset in assets}
        for spec in assets:
            # Context variables must be copied separately per submitted activity.
            future = self._executor.submit(copy_context().run, acquire_sidecar, spec, workspace, tracker, resources)
            self._futures[spec.id] = future
            if spec.required:
                future.add_done_callback(self._required_finished)

    def _required_finished(self, future: Future[AcquiredSidecar]) -> None:
        if not future.cancelled():
            error = future.exception()
            if error is not None and not isinstance(error, DownloadCancelled):
                self._tracker.fail(error)

    def get(self, asset_id: str) -> AcquiredSidecar | None:
        if asset_id in self._resolved:
            return self._resolved[asset_id]
        future = self._futures[asset_id]
        if not future.done():
            self._tracker.focus(f"acquire:{asset_id}")
        try:
            result = future.result()
            self._resolved[asset_id] = result
            return result
        except DownloadCancelled:
            raise
        except Exception:
            spec = self._specs[asset_id]
            if spec.required:
                raise
            self._resolved[asset_id] = None
            self._tracker.skip(f"acquire:{asset_id}", f"Optional {spec.kind} is unavailable")
            return None

    def close(self) -> None:
        # Cancellation is cooperative through the tracker/HTTP context. Calling
        # Future.cancel() alone cannot stop a running urllib request.
        self._executor.shutdown(wait=True, cancel_futures=True)
