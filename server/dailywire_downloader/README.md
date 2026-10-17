# Download execution

A provider-independent download engine. Playback URL discovery, profile interpretation,
output naming and NFO generation happen in the application **before** calling this package.
The downloader accepts a resolved URL and explicit processing options, never imports the
application domain, and never queries a database. HLS segment URL resolution is part of
transferring a supplied playlist, not provider URL discovery.

## Public interface and CLI

Python callers use the flat `download_media(url, destination, **options)` interface:

```python
from dailywire_downloader import SidecarSpec, download_media

execution = download_media(
    "https://cdn.example/episode.mp4",
    "/media/episode.mp4",
    transfer="file", download_mode="temporary",
    metadata_tags={"title": "Example episode"},
    sidecars=(SidecarSpec("description", "nfo", content=b"<movie/>", extension="nfo"),),
)
try:
    # Application code persists artifact identities and history here.
    pass
finally:
    execution.cleanup_workspace()
```

For an application transaction that fails, use `execution.rollback()` before
`execution.cleanup_workspace()`. Clients may supply a `DownloadTracker`, a progress callback,
resource limits, and lifecycle observers without introducing package dependencies on a scheduler.

Command-line use needs no WireLoft services:

```sh
dailywire-downloader download "https://cdn.example/video.mp4" "/media/video.mp4" \
  --metadata title="Example" --sidecar cover="https://cdn.example/cover.jpg" \
  --artwork cover
dailywire-downloader download "https://cdn.example/720.m3u8" "/media/video.mp4" \
  --transfer hls --remux-to-mp4 --generated-sidecar info=movie.nfo
```

Use `--sidecars-json specs.json` for optional assets, custom publication suffixes,
size limits and exact retry behavior. A JSON element has the fields of `SidecarSpec`;
`content_file` may be supplied instead of `content`.

For `--transfer hls_bundle`, supply each rendition explicitly using
`--hls-rendition 480=https://cdn.example/480.m3u8`, repeating for additional
heights. The engine accepts any explicitly selected set of renditions and validates
the URLs against the master without selecting or replacing them. WireLoft chooses
480p, 720p and 1080p for its existing HLS media profiles.
The downloader deliberately has no `probe` command because format selection
and playback URL discovery belong upstream.


`dailywire_downloader` is a standalone package: it does not import WireLoft's ORM,
settings, HTTP response models, or task scheduler. It owns transfer, auxiliary
acquisition, media rewrites, capacity limits, publication and filesystem recovery.

## Plan before execution

The `download_media` facade constructs a plan from explicit arguments;
advanced callers can still use `build_download_plan` with `execute_download_plan`.

`build_download_plan` returns an immutable `DownloadPlan`. Its inputs are resolved
source information, a concrete output path, storage policy, auxiliary asset specs,
and already-prepared container tags. The plan describes every required stage,
its dependencies, processing deadline, resource class and estimated work weight.
The tracker rejects unknown/cyclic dependencies and out-of-order stage execution.
The coordinator never
reads mutable application settings to make a later policy decision.

Signed URLs, actual response lengths, collision-resolved destination names and
cross-device rename outcomes are runtime facts. They are not persisted as part of
progress history. An unexpected cross-device move falls back to copying without
weakening collision safety.

`SidecarSpec` supports remote assets and locally generated content. It specifies
identity, kind, allowed format, size limit, retry policy, required/optional failure
behavior and final suffix. The same acquisition path supports artwork today and
language-specific subtitle sidecars such as `.en.srt` without another downloader.
Generated NFO content is not represented as a network request.

## Coordinator and application adapter

`execute_download_plan` consumes the plan and a `DownloadTracker`. Primary media
and auxiliary acquisition overlap; only stages requiring an asset wait for it.
FFmpeg mutations are serialized, and artwork plus container tags share one rewrite.
MP4 artwork uses native metadata atoms, because FFmpeg's arbitrary-key `mdta`
writer omits cover art. Standard title/show/episode tags are retained in that
mode; NFO remains the complete metadata representation for fields the container
cannot represent. Metadata-only MP4 output can use arbitrary-key `mdta` tags.
Media-transfer, auxiliary and local-processing capacity are independently bounded.

The returned `DownloadExecution` represents ready-to-commit outputs. The application
adapter records artifacts, asset identities and history and commits task success in
the same database transaction. A failed commit rolls back owned outputs before
cleaning the private workspace. A successful commit releases the recovery journal.
No progress writer remains active after the final transaction begins.

Cancellation is cooperative. The coordinator signals its owned work, stops local
processes and joins auxiliary workers before removing temporary files. A required
auxiliary failure stops the primary transfer; a permitted optional failure records
a warning. An asset-only retry does not restart the primary media download.

## Progress is a snapshot of facts

`DownloadSnapshot` identifies an attempt and ordered update sequence. Stages carry
activity codes, resource ownership, measured counters when available, wait intervals,
timestamps and deadlines. Primary-media completion releases transfer capacity but
is not operation success. Preparation and FFmpeg processing do not invent numerical
progress. Local copy counters remain available to batch estimators and diagnostics.

The Task Manager adapter persists these snapshots through the existing operation
puller. Individual UI components derive transfer percentage and labeled activity;
bulk coordinators calculate their own size-weighted work estimate. Batch manifests
are owned by the durable user operation, survive a replacement TaskRun, and record
whether a child is owned or merely reused. Cancellation never claims a reused child.

The watchdog uses activity and stage deadlines, not changing integer percentages.
History stores stage and wait intervals; overlapping durations must not be summed
as though they were sequential elapsed time. Transfer URLs and authorization data
are excluded from snapshots.

## Storage recovery

The storage package retains collision-safe reservations and same-filesystem final
renames. Cross-filesystem publication copies into a private destination-side file
before exposing its final name. Auxiliary files use a journal tied to the final
media basename. Recovery accepts an injected committed-artifact predicate; database
queries stay in the application layer. Unprovable ownership is preserved rather
than deleted. Generic relocation supports all tracked suffixes and internal rename
cycles, and is rolled back if the application transaction fails.
