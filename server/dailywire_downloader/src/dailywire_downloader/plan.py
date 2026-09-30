"""Immutable, storage-independent decisions for a single download attempt.

The application supplies resolved source/domain values. Planning performs no
network requests, filesystem writes, database work or scheduler lookups. Runtime
facts (a response's actual size, a collision-resolved name) do not change policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .errors import DownloadError

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
    if (metadata_tags or artwork_asset_id) and source.extension not in {"mp4", "m4a", "m4v", "mp3", "mkv"}:
        raise DownloadError(f"Cannot embed artwork or metadata in .{source.extension}; select sidecars or an MP4 output")
    suffixes = [a.target_suffix for a in assets if a.publish and a.target_suffix]
    if len(set(suffixes)) != len(suffixes):
        raise ValueError("Two assets cannot publish the same sidecar suffix")
    if any(s == Path(requested_destination).suffix for s in suffixes):
        raise ValueError("An asset cannot replace the primary media")

    copying = download_mode == "temporary" and publication_requires_copy(str(temporary_root), str(requested_destination))
    # Work units are estimates for batch aggregation, not time estimates. One
    # full-media pass is one unit. Tiny assets cannot dominate a movie's work.
    media_bytes = max(1, source.expected_bytes or 100 * 1024 * 1024)
    stages = [
        StageSpec("prepare", "prepare", "preparing", weight=0.02),
        StageSpec("media", "download_media", "transferring", "media"),
    ]
    for asset in assets:
        weight = max(0.002, (len(asset.content) if asset.content is not None else 512 * 1024) / media_bytes)
        stages.append(StageSpec(
            f"acquire:{asset.id}", "generate_sidecar" if asset.content is not None else "download_sidecar",
            "transferring", "sidecar", weight, asset.id,
        ))
    if source.remux_to_mp4:
        stages.append(StageSpec("remux", "remux", "finishing", "processing"))
    if metadata_tags or artwork_asset_id:
        code = "embed_artwork_metadata" if metadata_tags and artwork_asset_id else "embed_artwork" if artwork_asset_id else "embed_metadata"
        stages.append(StageSpec("embed", code, "finishing", "processing"))
    stages.append(StageSpec("publish", "publish_media", "finishing", "processing", 1.0 if copying else 0.01))
    for asset in assets:
        if asset.publish:
            stages.append(StageSpec(f"publish:{asset.id}", "publish_sidecar", "finishing", "none", 0.002, asset.id))
    stages.extend((
        StageSpec("verify", "verify", "finishing", weight=0.01),
        StageSpec("finalize", "finalize", "finishing", weight=0.01),
    ))
    return DownloadPlan(
        attempt_id or str(uuid4()), source, str(requested_destination), download_mode,
        str(temporary_root), ffmpeg_path, tuple(assets), tuple(metadata_tags),
        artwork_asset_id, tuple(stages), copying,
    )
