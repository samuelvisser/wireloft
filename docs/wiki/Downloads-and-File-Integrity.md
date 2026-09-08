# Downloads and File Integrity

WireLoft's Downloads area tracks the concrete media files produced by Download Profiles and manual movie/episode downloads. This is separate from the profile definitions themselves: profiles describe desired behavior, while download records describe actual work and files.

## Download lifecycle

A download is associated with:

- a media item such as an episode, movie, or movie extra;
- a Local Media Profile, which determines format and output path;
- status/progress information;
- the final path and recorded artifact identity when the download completes.

WireLoft can keep multiple local variants of the same episode because different Local Media Profiles represent different formats/output destinations.

## Concurrency and retries

Global defaults are:

```text
Maximum concurrent downloads: 5
Maximum download attempts:    3
Download timeout:             600 seconds
```

These apply across Download Profiles. Reducing concurrency can help on slower storage/network connections; increasing it beyond available bandwidth or disk throughput may make overall performance worse.

## Video remuxing

By default, WireLoft remuxes downloaded HLS video into MP4:

```yaml
downloadSettings:
  remuxVideoToMp4: true
  ffmpegPath: ffmpeg
```

This is a **lossless container change**, not a video re-encode. It is intended to produce a conventional MP4 file quickly without changing the encoded video/audio streams.

FFmpeg must be available at the configured path.

## Output paths

The Local Media Profile renders a virtual path beginning with `/downloads/`. WireLoft maps that prefix to `downloadSettings.downloadRoot`.

In the supplied Docker configuration:

```yaml
downloadSettings:
  downloadRoot: /downloads
```

The host bind mount then determines where that directory lives physically.

See [[Local-Media-Profiles]] for template syntax and filename sanitization.

## Download logs

WireLoft exposes download status/log information in the UI so failed media does not have to be diagnosed only from container logs. When investigating a failed item, check the specific download record first, then global application logs if the failure is upstream or infrastructure-related.

## Scheduled verification

WireLoft runs a download-verification job every two hours by default:

```text
0 */2 * * *
```

Configure this with `downloadSettings.verifyDownloadsCron`.

## File watcher

The file watcher is enabled by default and scans every ten minutes:

```text
*/10 * * * *
```

Its job is to reconcile WireLoft's recorded downloaded files with the filesystem.

### Missing and renamed files

If the path stored on a download record no longer exists, WireLoft first checks that file's original directory for a rename. It uses filesystem device/inode identity where useful and confirms/falls back to a lightweight sampled content fingerprint, so the same behavior also works on SMB/NFS-style mounts where filesystem identifiers can be unstable.

If exactly one matching file is found, WireLoft updates the recorded path. It deliberately does not search other directories. Files should be moved to a different directory by changing the Local Media Profile output template so WireLoft performs the move itself.

If no unique same-directory match exists, the artifact is marked missing.

The same reconciliation path is also used on demand whenever WireLoft needs an existing downloaded file. RSS delivery, file renaming, replacement/re-download flows, and retention/deletion therefore attempt same-directory rename recovery before treating the recorded path as unavailable. A successfully recovered path is persisted before the caller continues using the file.

### File-size verification

With the default:

```yaml
fileWatcher:
  verifyFileSize: true
```

WireLoft also treats a file as corrupted when it is empty or smaller than the size recorded when the download completed.

This remains a lightweight integrity check, not continuous full-file checksum verification. The sampled fingerprint used for rename identity is not used to re-hash every healthy file on every watcher run.

## Filename compatibility

The global filename-restriction mode is applied when output templates are rendered. The default `windows` mode is designed to remain usable on Windows while preserving Unicode where possible.

Use `restricted` for conservative ASCII-style filenames or `unrestricted` when you specifically want more original punctuation/Unicode and do not require Windows compatibility.

See [[Local-Media-Profiles#filename-restrictions]].

## Retention/deletion

Automatic deletion is primarily controlled by Podcast Download Profiles. A rolling date/episode-count limit can optionally delete downloads that fall outside the active window.

A limit without **Delete older episodes** affects what new content should be downloaded but does not automatically prune older media already retained.

See [[Download-Profiles]].

## RSS interaction

RSS profiles that enable **Use Downloads** search local artifact records for the best match. Before a candidate is rejected as unavailable, WireLoft reconciles its recorded path through the same file-watcher logic, so a same-directory manual rename can be recovered and served immediately.

If no suitable local file can be resolved:

- with Daily Wire fallback enabled, the feed can still stream remotely;
- with downloads-only mode, the episode may no longer have an available enclosure.

See [[Podcast-RSS-Feeds]].