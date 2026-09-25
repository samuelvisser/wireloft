# Troubleshooting

Start with the symptom you can see in the WireLoft interface. The **Home** page highlights downloads and movie metadata that need attention, while individual downloads have their own logs.

For exact setting names and defaults, see [[Settings]].

## A new episode is not visible yet

1. Open the show and check its recent sync history.
2. Use **Sync now** if you do not want to wait for the next automatic check.
3. If a sync completed but found nothing, Daily Wire may not be exposing the episode to WireLoft yet.
4. If the episode is already listed but is live or still publishing, WireLoft will continue monitoring it automatically.

New-episode discovery runs every **30 minutes** by default. Known episodes that are still publishing are checked every **2 minutes**.

## An episode has an old title, image, or number

Daily Wire can change metadata after publication. WireLoft refreshes recently published episode metadata by default after:

```text
15m,30m,1h,3h,6h,24h,3d
```

Use **Sync now** when you want to check the show immediately. If the problem persists much longer, check the Daily Wire version itself to confirm whether the upstream metadata has actually changed.

## A live episode has no download yet

Seeing an episode in the Library does not necessarily mean final downloadable media is ready.

For Podcast Download Profiles, check:

- **Download with countdown** — whether WireLoft may download the early countdown version;
- **Redownload final version** — whether an early copy should later be replaced;
- whether the profile's episode types include this item.

If countdown downloading is disabled, waiting for the final version is expected behavior.

## WireLoft stopped discovering episodes automatically

Check:

- **Settings → Automation → Enable background scheduler** is enabled;
- the **Find new episodes** schedule is valid;
- `TZ` is correct;
- Home/download logs for recent errors;
- the Daily Wire connection when the show requires member access.

Try **Sync now** on one show. If manual sync works, the problem is more likely related to scheduling than Daily Wire access.

## Downloads stay queued

WireLoft allows **5 simultaneous downloads** by default. When all slots are occupied, additional items wait as Queued.

You can use **Prioritize** on a queued item when you want it selected before ordinary queued work as soon as a slot becomes available.

If nothing is actually downloading, check Home and the Downloads page for failed or stalled work.

## Downloads are slow

Check:

- **Concurrent downloads**;
- internet bandwidth;
- disk or NAS performance;
- whether several downloads are also being processed by FFmpeg;
- Daily Wire connectivity.

Increasing concurrency can make performance worse when the real bottleneck is storage, CPU, or bandwidth.

## A download failed

Open its **Download log** first. Common causes include:

- a temporary internet problem;
- Daily Wire media not being available yet;
- expired or unavailable upstream media;
- authentication/membership problems;
- storage permission or capacity problems;
- FFmpeg errors during local processing.

Use **Retry** once the underlying problem is resolved.

## Video was not produced as MP4

Check **Settings → Downloads**:

- **Remux downloaded video to MP4** is enabled;
- **FFmpeg executable** points to a working FFmpeg installation.

The normal Docker image already includes FFmpeg.

Remuxing changes the container format without re-encoding the video.

## Temporary download mode is not writing to the final library yet

That is expected while the download or local processing is incomplete.

With **Save to temporary folder first**, WireLoft keeps incomplete work in the configured temporary folder and only publishes the completed media into its final destination afterwards.

Check the Download page for the current progress/status before looking for the final file.

## A downloaded file is marked Missing

WireLoft could no longer find the completed file at the path it recorded.

Check:

- whether the file was manually moved or renamed;
- whether the download/root mount changed;
- whether a NAS or network share is currently mounted and reachable;
- permissions on the media directory.

WireLoft can recover some same-folder renames, but it is not a general filesystem index and may not follow a file moved into another directory.

## A file is marked Corrupted

With **Verify file size** enabled, WireLoft considers a completed file corrupted when it is empty or smaller than the size recorded when the download completed.

Check the actual file and storage health. If the storage is healthy and you want a fresh copy, use **Retry**.

## Output paths contain unexpected characters

Check **Settings → Downloads → Filename restrictions**:

- **Minimal restrictions** preserves most punctuation and Unicode;
- **Windows-compatible filenames** removes characters Windows cannot safely use;
- **Restricted filenames** creates conservative ASCII-style names.

See [[Local-Media-Profiles#filename-restrictions]].

## A Local Media Profile template will not save

Check that:

- the rendered path begins with `/downloads/`;
- the template ends with `.ext`;
- variables are available for that profile type;
- the Jinja syntax is valid;
- a Movie profile includes an item-specific value such as `{{ title }}` or `{{ media_type }}` so movies and extras cannot use the same path.

Jinja setup statements may appear before `/downloads/` as long as they do not output text.

Use the template editor's preview and variable picker to locate the problem. See [[Local-Media-Profiles]].

## A setting ignores the value saved in the UI

An environment variable may be overriding it.

The Settings page identifies fields controlled by environment variables. Change the deployment value instead of repeatedly changing the UI field.

For normal use, precedence is:

```text
environment > config.yml > defaults
```

The timezone uses `TZ`.

## The Settings UI did not write every default to `config.yml`

That is normal. WireLoft stores only values you changed. Missing keys continue to use their current defaults.

## RSS feed returns 404 or is unavailable

Check:

- the Stream Profile is enabled;
- the URL uses the current token;
- the token was not regenerated while the podcast app still has the old URL;
- your reverse proxy forwards `/feeds/rss/` to WireLoft.

## RSS feed is empty or some episodes are missing

Check:

- at least one of **Use Downloads** or **Use DailyWire stream** is enabled;
- selected episode types;
- preferred format;
- **Prefer exact match**;
- **Maximum episodes in RSS feed**.

A downloads-only feed cannot expose media for an episode when no acceptable completed local download exists.

## RSS works in a browser but not in the podcast app

The browser and podcast app may not be using the same network path.

Check:

- whether the hostname is LAN-only;
- DNS from the client;
- HTTPS certificate validity;
- firewall/VPN access;
- reverse-proxy forwarding for `/feeds/rss/` media as well as the XML feed;
- whether the podcast provider fetches feeds from cloud servers instead of directly from your device.

The Stream Profile URL can be edited to use the correct reachable hostname while retaining its token/path.

## RSS video plays as audio

When using **Podcasting 2.0 direct stream with audio fallback**, the podcast app may not support the video stream method correctly and may choose the audio fallback.

Try **Serve as locally cached MP4** for broader video compatibility or **Direct stream with cached MP4 fallback**.

## RSS MP4 takes a long time to start

If the episode is not already downloaded or cached, WireLoft must prepare the complete MP4 before conventional playback can begin.

For faster access to recent episodes, keep a small recent video window downloaded locally and enable **Use Downloads** on the RSS profile.

## Premium Daily Wire media fails

Open **Settings → DailyWire** and confirm WireLoft is still connected. Also confirm that the same account still has access to the content on Daily Wire itself.

If you changed advanced endpoints, OAuth settings, or request pacing, restore their defaults before continuing diagnosis.

## WireLoft says an episode has no usable media

Daily Wire can temporarily list an episode before usable media is available, or an old placeholder can remain in the catalog.

WireLoft rechecks these episodes every **20 minutes** by default. It normally waits **4 hours** before an episode that remains unavailable can be cleaned up.

If you are certain the entry should be removed immediately, use **Early Delete** from the episode actions. WireLoft checks its current Daily Wire state again before removal.

## Database errors or `database disk image is malformed`

Stop WireLoft before doing anything else and make a copy of the complete `/config` directory.

Do not run multiple WireLoft backends against the same SQLite database. A common development mistake is running a local backend and a Docker instance that both use the same `wireloft.db` at the same time.

If the database reports structural corruption, restore a known-good `/config` backup when available. Avoid repeatedly restarting or running migration commands against a database that is already reporting corruption.

See [[Backups-and-Upgrades]].

## Problems after restoring a backup

Make sure you restored the **entire `/config` directory**, not only `wireloft.db`. The application key and Daily Wire authentication state live alongside the database/configuration.

If the hostname changed, update RSS Stream Profile URLs as well.