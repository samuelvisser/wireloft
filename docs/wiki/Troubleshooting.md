# Troubleshooting

This page starts with the subsystem most likely to explain each symptom. For exact defaults and environment-variable mappings, see [[Settings]].

## A new episode is not visible yet

1. Open the show and check its recent sync log.
2. If the last scheduled discovery has not run yet, use **Sync now** for that show.
3. If a sync ran and found `0`, Daily Wire may not yet be exposing the episode through the endpoint WireLoft uses.
4. If the episode exists but is live/not final, WireLoft's faster episode monitor handles it separately from normal discovery.

Default discovery is every 30 minutes; known not-yet-final episodes are monitored every minute.

## An episode has an old title or placeholder thumbnail

New/live Daily Wire metadata can change after publication. WireLoft performs targeted metadata refreshes by default at:

```text
5m,15m,30m,1h,3h,6h,24h
```

That avoids continuously rescanning the complete library just to catch changes to newly published episodes.

If you changed `newEpisodeSchedule.metadataRefreshIntervals`, verify the sequence is valid and strictly increasing.

## A live episode does not have a download

An indexed episode does not necessarily mean final downloadable media is ready. Podcast Download Profiles can either wait past the countdown stage or deliberately download the early countdown version.

Check:

- **Download with countdown**;
- **Redownload final version**;
- `episodeStatusTiming.publishedCountdownAfterMinutes`;
- `episodeStatusTiming.publishedFinalAfterMinutes`.

## WireLoft stopped discovering new episodes automatically

Check:

- `scheduler.enabled` is `true`;
- `newEpisodeSchedule.findEpisodesCron` is a valid five-field cron expression;
- the container timezone (`TZ`) is what you expect;
- logs for task failures/retries;
- Daily Wire authentication if the show requires member access.

A manual **Sync now** can help distinguish a scheduler problem from a Daily Wire/API problem.

## Downloads are queued or slow

Check the global limits:

- `downloadSettings.maxConcurrentDownloads` — default `5`;
- `downloadSettings.maxDownloadAttempts` — default `3`;
- `downloadSettings.downloadTimeoutSeconds` — default `600`;
- scheduler worker availability.

Increasing concurrency is not always beneficial: source bandwidth, disk throughput, FFmpeg work, and Daily Wire request pacing can become the bottleneck.

## Video downloaded as TS instead of MP4

`downloadSettings.remuxVideoToMp4` is enabled by default. If remuxing is expected, verify:

- the setting is `true`;
- `downloadSettings.ffmpegPath` points to a working FFmpeg executable;
- FFmpeg is available inside the environment/container where WireLoft runs.

The remux is a container-format change, not a video re-encode.

## A downloaded file is marked missing

WireLoft stores the path associated with a completed download. The file watcher checks that recorded path on disk.

If a managed file is manually renamed or moved outside WireLoft, the old path can be reported missing. The file watcher is not a general rename-tracking filesystem index.

Also verify `downloadSettings.downloadRoot` and the host volume mapping did not change.

## A file is marked corrupted

With `fileWatcher.verifyFileSize=true`, WireLoft flags a download when the file is empty or smaller than the size recorded when the download originally completed.

Check the actual file size and storage health before forcing a re-download.

## Output paths contain unexpected characters

Check `downloadSettings.filenameRestrictionMode`:

- `unrestricted` preserves most Unicode/punctuation;
- `windows` removes Windows-incompatible characters and reserved names;
- `restricted` reduces names to conservative ASCII-style characters.

See [[Local-Media-Profiles#filename-restrictions]].

## A Local Media Profile template will not save

Templates must:

- start with `/downloads/`;
- end with `.ext`;
- use only variables valid for the profile type;
- contain valid Jinja syntax;
- for movies, contain at least one item-specific value so a movie and its extras cannot collide.

Use the template preview to identify the problematic segment. See [[Local-Media-Profiles]].

## A setting keeps changing back or ignores `config.yml`

An environment variable probably has higher priority.

WireLoft precedence is:

```text
internal kwargs > environment > .env > config.yml > file secrets > defaults
```

For example, `WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS` overrides `downloadSettings.maxConcurrentDownloads` in YAML.

Timezone is the exception: use `TZ`, not `WL_TIMEZONE`.

## The Settings UI did not write every default into `config.yml`

That is expected. WireLoft keeps the configuration sparse and only writes changed fields. Missing YAML keys use the current built-in defaults.

The Docker seed also runs only once, when `config.yml` is absent.

## RSS feed returns 404

Check:

- the Stream Profile is enabled;
- the URL contains the current token;
- you did not regenerate the token and leave the old URL in the client;
- the reverse proxy forwards `/feeds/rss/...` to WireLoft.

An unknown, rotated, or disabled tokenized feed is intentionally unavailable.

## RSS feed is empty

Check that at least one source is enabled:

- **Use Downloads**; and/or
- **Use DailyWire stream**.

Then verify the selected episode types. For downloads-only feeds, the episodes also need suitable completed local files.

## RSS works in a browser but not in the podcast app

The browser and podcast app may not be using the same network path.

Check:

- whether the feed hostname is LAN-only;
- DNS from the client;
- HTTPS certificate validity;
- reverse-proxy forwarding for both feed XML and enclosure URLs;
- whether the podcast service fetches feeds from a cloud server rather than directly from your device.

The RSS feed URL is editable, so replace an internal hostname with the correct reachable hostname while preserving the token/path.

## RSS video plays as audio

If the profile uses **Podcasting 2.0 direct stream with audio fallback**, the podcast client may be ignoring the HLS alternate enclosure and using the conventional audio enclosure instead.

Try:

- **Serve as locally cached MP4** for conventional video compatibility; or
- **Direct stream with cached MP4 fallback**.

See [[Podcast-RSS-Feeds#daily-wire-video-delivery-methods]].

## RSS MP4 takes a long time to start

When an episode is not already downloaded/cached, WireLoft may need to prepare the complete MP4 before a normal video enclosure can be served.

For faster recent playback, create a video Download Profile that keeps only the latest 5 episodes and enable **Use Downloads** on the RSS profile.

## Some RSS episodes are unexpectedly absent

Review:

- episode-type selection;
- preferred format;
- **Require exact match**;
- whether **Use Downloads** and/or **Use DailyWire stream** is enabled;
- **Maximum episodes in RSS feed**.

A downloads-only feed omits an episode when no acceptable completed local file exists.

## Premium Daily Wire media fails

Confirm the Daily Wire account connected to WireLoft still authenticates and has access to the requested member-exclusive content.

The WireLoft RSS token is not a Daily Wire entitlement; it only grants access to the feed capability configured on your instance.

## Daily Wire requests fail after changing advanced endpoint settings

Restore the production defaults unless you intentionally know you need a different endpoint:

```yaml
dwApi:
  middlewareApi: https://middleware-prod.dailywire.com/middleware
  streamApi: https://stream.media.dailywire.com

dwOauth:
  issuer: https://authorize.dailywire.com
  audience: https://api.dailywire.com/
```

The OAuth client ID/scope and request-throttling settings should also generally remain at their defaults.

## After restoring a backup, sessions or authentication behave strangely

Make sure you restored the **entire `/config` directory**, not only `wireloft.db`. The application secret and Daily Wire authentication state live alongside the database/configuration.

See [[Backups-and-Upgrades]].