"""Immutable, storage-independent decisions for a single download attempt.

The application supplies resolved source/domain values. Planning performs no
network requests, filesystem writes, database work or scheduler lookups. Runtime
facts (a response's actual size, a collision-resolved name) do not change policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from math import isfinite
from typing import Literal
from uuid import uuid4

from .errors import DownloadError
from .storage.filesystem import FilesystemStorageKind, inspect_filesystem

Phase = Literal["preparing", "transferring", "finishing", "complete"]
Resource = Literal["none", "media", "sidecar", "processing"]


@dataclass(frozen=True)
class ResolvedDownloadSource:
    url: str
    format_downloaded: str
    use_hls: bool
    remux_to_mp4: bool
    extension: str
    audio_only: bool
    hls_bundle: bool = False
    expected_bytes: int | None = None
    convert_video_to_m4a: bool = False


@dataclass(frozen=True)
class SidecarSpec:
    """An auxiliary asset: acquire once, then embed and/or publish it.

    target_suffix is a suffix, never a relative path (for example '.en.srt').
    A missing suffix uses the format returned by the remote server. Generated
    assets carry their exact immutable payload instead of pretending to be HTTP.
    """
    id: str
    kind: str
    url: str | None = None
    content: bytes | None = None
    extension: str = "bin"
    target_suffix: str | None = None
    publish: bool = True
    required: bool = True
    maximum_bytes: int = 32 * 1024 * 1024
    attempts: int = 3
    allowed_extensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in self.id):
            raise ValueError("Asset IDs must contain lowercase letters, numbers, '-' or '_'")
        if (self.url is None) == (self.content is None):
            raise ValueError("An asset needs exactly one URL or generated payload")
        if self.url is not None and not self.url.startswith(("https://", "http://")):
            raise ValueError("Remote assets require an HTTP(S) URL")
        if not self.extension.isalnum():
            raise ValueError("Invalid asset extension")
        if self.target_suffix is not None and (
            not self.target_suffix.startswith(".")
            or "/" in self.target_suffix or "\\" in self.target_suffix
            or ".." in self.target_suffix or "\0" in self.target_suffix
        ):
            raise ValueError("Asset publication suffix must not contain a path")
        if self.maximum_bytes <= 0 or self.attempts < 1:
            raise ValueError("Asset size limit and attempt count must be positive")
        if self.content is not None and len(self.content) > self.maximum_bytes:
            raise ValueError("Generated asset exceeds its size limit")


@dataclass(frozen=True)
class StageSpec:
    id: str
    code: str
    phase: Phase
    resource: Resource = "none"
    weight: float = 1.0
    asset_id: str | None = None
    depends_on: tuple[str, ...] = ()
    deadline_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.weight) or self.weight < 0:
            raise ValueError("Stage work weights must be finite and nonnegative")
        if self.deadline_seconds is not None and (
            not isfinite(self.deadline_seconds) or self.deadline_seconds <= 0
        ):
            raise ValueError("Stage deadlines must be finite and positive")


@dataclass(frozen=True)
class DownloadPlan:
    attempt_id: str
    source: ResolvedDownloadSource
    requested_destination: str
    download_mode: Literal["direct", "temporary"]
    temporary_root: str
    ffmpeg_path: str
    assets: tuple[SidecarSpec, ...]
    metadata_tags: tuple[tuple[str, str], ...]
    artwork_asset_id: str | None
    stages: tuple[StageSpec, ...]
    publication_requires_copy: bool
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        stages = {stage.id: stage for stage in self.stages}
        if len(stages) != len(self.stages):
            raise ValueError("Stage IDs must be unique within an attempt")
        if not {"prepare", "media", "publish", "verify", "finalize"} <= stages.keys():
            raise ValueError("The download plan is missing a required lifecycle stage")
        for stage in self.stages:
            if any(dependency not in stages for dependency in stage.depends_on):
                raise ValueError(f"Unknown dependency in stage '{stage.id}'")
        pending = dict(stages)
        completed: set[str] = set()
        while pending:
            ready = {name for name, stage in pending.items() if set(stage.depends_on) <= completed}
            if not ready:
                raise ValueError("Download stage dependencies contain a cycle")
            completed.update(ready)
            for name in ready:
                del pending[name]

    def stage(self, stage_id: str) -> StageSpec:
        return next(stage for stage in self.stages if stage.id == stage_id)


def _existing_ancestor(path: Path) -> Path:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def publication_requires_copy(temporary_root: str, destination: str) -> bool:
    """Inspect storage without creating destination directories early."""
    try:
        return (
            _existing_ancestor(Path(temporary_root)).stat().st_dev
            != _existing_ancestor(Path(destination).parent).stat().st_dev
        )
    except OSError:
        return True


def _processing_weights(storage_kind: FilesystemStorageKind) -> tuple[float, float]:
    """Estimate stream-copy work from the filesystem that hosts intermediate media."""
    if storage_kind is FilesystemStorageKind.LOCAL:
        return 0.08, 0.08
    if storage_kind is FilesystemStorageKind.REMOTE:
        return 0.55, 0.60
    if storage_kind is FilesystemStorageKind.SHARED_OR_VIRTUAL:
        return 0.20, 0.20
    return 0.60, 0.60


def _publication_weight(storage_kind: FilesystemStorageKind, *, copying: bool) -> float:
    if not copying:
        return 0.01
    if storage_kind is FilesystemStorageKind.REMOTE:
        return 0.12
    if storage_kind is FilesystemStorageKind.LOCAL:
        return 0.08
    if storage_kind is FilesystemStorageKind.SHARED_OR_VIRTUAL:
        return 0.12
    return 0.25


def build_download_plan(
    *,
    source: ResolvedDownloadSource,
    requested_destination: str | Path,
    download_mode: Literal["direct", "temporary"],
    temporary_root: str | Path,
    ffmpeg_path: str = "ffmpeg",
    assets: tuple[SidecarSpec, ...] = (),
    metadata_tags: tuple[tuple[str, str], ...] = (),
    artwork_asset_id: str | None = None,
    attempt_id: str | None = None,
) -> DownloadPlan:
    """Resolve optional work once; the coordinator executes this plan verbatim."""
    if download_mode not in ("direct", "temporary"):
        raise ValueError("Unknown download storage mode")
    if len({asset.id for asset in assets}) != len(assets):
        raise ValueError("Asset IDs must be unique within an attempt")
    if artwork_asset_id is not None and not any(a.id == artwork_asset_id for a in assets):
        raise ValueError("Embedded artwork must reference a planned asset")
    if source.hls_bundle and (metadata_tags or artwork_asset_id):
        raise DownloadError("HLS bundles support sidecars, not container embedding")
    if source.remux_to_mp4 and source.convert_video_to_m4a:
        raise DownloadError("A source cannot be remuxed to MP4 and converted to M4A")
    if source.convert_video_to_m4a and (not source.audio_only or source.extension != "m4a"):
        raise DownloadError("Video-to-M4A conversion requires an audio-only M4A output")
    if (metadata_tags or artwork_asset_id) and source.extension not in {"mp4", "m4a", "m4v", "mp3", "mkv"}:
        raise DownloadError(f"Cannot embed artwork or metadata in .{source.extension}; select sidecars or an MP4 output")
    suffixes = [a.target_suffix for a in assets if a.publish and a.target_suffix]
    if len(set(suffixes)) != len(suffixes):
        raise ValueError("Two assets cannot publish the same sidecar suffix")
    if any(s == Path(requested_destination).suffix for s in suffixes):
        raise ValueError("An asset cannot replace the primary media")

    copying = download_mode == "temporary" and publication_requires_copy(str(temporary_root), str(requested_destination))
    processing_path = Path(temporary_root) if download_mode == "temporary" else Path(requested_destination).parent
    processing_storage = inspect_filesystem(processing_path).storage_kind
    destination_storage = inspect_filesystem(Path(requested_destination).parent).storage_kind
    remux_weight, embed_weight = _processing_weights(processing_storage)
    publish_weight = _publication_weight(destination_storage, copying=copying)

    # Work units are estimates for batch aggregation.
    media_bytes = max(1, source.expected_bytes or 100 * 1024 * 1024)
    stages = [
        StageSpec("prepare", "prepare", "preparing", weight=0.02),
        StageSpec("media", "download_media", "transferring", "media", depends_on=("prepare",)),
    ]
    for asset in assets:
        weight = max(0.002, (len(asset.content) if asset.content is not None else 512 * 1024) / media_bytes)
        stages.append(StageSpec(
            f"acquire:{asset.id}", "generate_sidecar" if asset.content is not None else "download_sidecar",
            "transferring", "sidecar", weight=weight, asset_id=asset.id, depends_on=("prepare",),
        ))
    # Dependencies and deadlines are policy, not runtime decisions. Auxiliary
    # acquisition depends only on preparation; local media conversion can
    # overlap it, whereas embedding must await its artwork. The tracker enforces
    # these boundaries.
    media_ready = "media"
    if source.remux_to_mp4:
        stages.append(StageSpec(
            "remux", "remux", "finishing", "processing", weight=remux_weight,
            depends_on=(media_ready,), deadline_seconds=3600,
        ))
        media_ready = "remux"
    if source.convert_video_to_m4a:
        stages.append(StageSpec(
            "convert_audio", "convert_audio", "finishing", "processing", weight=remux_weight,
            depends_on=(media_ready,), deadline_seconds=3600,
        ))
        media_ready = "convert_audio"
    if metadata_tags or artwork_asset_id:
        code = "embed_artwork_metadata" if metadata_tags and artwork_asset_id else "embed_artwork" if artwork_asset_id else "embed_metadata"
        dependencies = (media_ready,) + ((f"acquire:{artwork_asset_id}",) if artwork_asset_id else ())
        stages.append(StageSpec(
            "embed", code, "finishing", "processing", weight=embed_weight,
            depends_on=dependencies, deadline_seconds=3600,
        ))
        media_ready = "embed"
    stages.append(StageSpec(
        "publish", "publish_media", "finishing", "processing", weight=publish_weight,
        depends_on=(media_ready, *(f"acquire:{asset.id}" for asset in assets)),
        deadline_seconds=3600,
    ))
    for asset in assets:
        if asset.publish:
            stages.append(StageSpec(
                f"publish:{asset.id}", "publish_sidecar", "finishing", "none", 0.002, asset.id,
                depends_on=("publish", f"acquire:{asset.id}"), deadline_seconds=1800,
            ))
    stages.extend((
        StageSpec(
            "verify", "verify", "finishing", weight=0.01,
            depends_on=("publish", *(f"publish:{asset.id}" for asset in assets if asset.publish)),
            deadline_seconds=120,
        ),
        StageSpec("finalize", "finalize", "finishing", weight=0.01,
                  depends_on=("verify",), deadline_seconds=120),
    ))
    return DownloadPlan(
        attempt_id or str(uuid4()), source, str(requested_destination), download_mode,
        str(temporary_root), ffmpeg_path, tuple(assets), tuple(metadata_tags),
        artwork_asset_id, tuple(stages), copying,
    )
