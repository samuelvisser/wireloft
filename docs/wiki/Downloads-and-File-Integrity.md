# Downloads and File Integrity

The **Downloads** page is the central place to see actual media-file activity in WireLoft. Profiles describe what WireLoft should do; this page shows what has actually been queued, downloaded, processed, or failed.

Each row represents one media item and Local Media Profile combination, so the same episode can appear more than once when you keep multiple formats.

## Download statuses

WireLoft can show downloads as:

- **Queued** — waiting for a download slot;
- **Downloading** — media is currently being transferred;
- **Local processing** — the primary media transfer finished, but local work such as MP4 remuxing, thumbnail handling, or final publication is still happening;
- **Downloaded** — the local file completed successfully;
- **Cancelled** — the download was stopped;
- **Error** — the attempt failed;
- **Missing** — WireLoft expected a completed file but cannot find it;
- **Corrupted** — the file exists but failed WireLoft's integrity checks.

Completed downloads are hidden by the default Downloads-page filter so active/problems are easier to see. Enable the **Downloaded** filter when you want full history.

## Download actions

Available actions depend on the current state.

### Prioritize a queued download

A queued item can be **Prioritized**. Prioritized items are chosen before ordinary queued work when the next download slot becomes available. If several queued items are prioritized, the order in which they were prioritized is respected.

### Cancel

Active or queued work can be cancelled. Cancellation stops the WireLoft download operation; it does not delete a previously completed media file.

### Retry

Failed, cancelled, missing, or corrupted downloads can be retried where appropriate. Queued items do not show Retry because they have not failed—they can be prioritized instead.

### Download log

Open the download log when you need to understand why a particular item failed or was retried. This is usually more useful than starting with the complete application log because it focuses on that media item.

## Download limits and retries

The system-wide defaults are:

| Setting | Default |
| --- | ---: |
| Concurrent downloads | 5 |
| Maximum attempts | 3 |
| Timeout per attempt | 600 seconds |

These are configured under **Settings → Downloads**.

Higher concurrency is not always faster. Your internet connection, Daily Wire, CPU, FFmpeg work, and storage can all become bottlenecks.

## Direct and temporary download modes

WireLoft supports two ways of handling incomplete downloads.

### Save directly to downloads

Download work happens in the destination area. This is the simpler option and is the system default.

### Save to temporary folder first

Incomplete download and processing work stays in the configured temporary folder. The completed media is placed in its final library location only when it is ready.

This is useful when a media server watches your final library and should never see partial files.

The system default is configured in **Settings → Downloads**, and individual Local Media Profiles can inherit or override it. See [[Local-Media-Profiles#download-behavior]].

## Video MP4 output

By default, WireLoft remuxes downloaded HLS video into MP4.

This changes the container format without re-encoding the video, so it is much faster than converting the video itself and does not intentionally reduce quality.

FFmpeg must be available at the configured path. The Docker image already includes it.

## Where files are stored

A Local Media Profile produces a path beginning with `/downloads/`. WireLoft resolves that against the configured **Download root**.

The supplied Docker setup mounts the host's `./downloads` directory at `/downloads` inside the container.

See [[Local-Media-Profiles]] for output templates and filename rules.

## Automatic file checks

WireLoft periodically checks recorded downloads so problems caused by external file changes do not remain invisible.

By default:

- download verification runs every **2 hours**;
- the file watcher checks tracked files every **10 minutes**.

These schedules can be changed in **Settings → Downloads**.

### Missing files and renames

When a completed file is no longer at its recorded path, WireLoft can recognize some same-folder renames and update the stored path automatically.

It does not treat your entire media library as a general filesystem index. If you manually move a file to another directory, WireLoft may mark the original download as missing.

For reorganizing WireLoft-managed media, change the Local Media Profile output template and use WireLoft's own workflow rather than moving files around externally whenever possible.

### File-size verification

With **Verify file size** enabled, WireLoft marks a completed file as corrupted if it is empty or smaller than the size recorded when the download completed.

This is a lightweight integrity safeguard. WireLoft does not continuously calculate a full checksum of every healthy media file.

If a file is marked corrupted, check the actual storage first if you suspect a disk, NAS, or filesystem problem, then use Retry when you want WireLoft to download it again.

## Retention and automatic deletion

Automatic retention for show episodes comes from Podcast Download Profiles.

A rolling date or episode-count limit can optionally delete downloads that fall outside the active window. If **Delete older episodes** is disabled, the limit affects new download selection but leaves older files already on disk alone.

See [[Download-Profiles]].

## RSS feeds and local files

An RSS Stream Profile with **Use Downloads** can serve suitable completed files from the download library.

If no acceptable local file is available:

- a hybrid feed can fall back to Daily Wire when **Use DailyWire stream** is also enabled;
- a downloads-only feed cannot serve that episode until a suitable local file exists.

See [[Podcast-RSS-Feeds]].