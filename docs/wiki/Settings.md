# Settings

WireLoft has one centralized settings model. Settings can come from `config.yml`, environment variables, a dotenv file, file secrets, or built-in defaults.

This page lists every configurable setting in WireLoft, its YAML key, environment-variable equivalent, default, and purpose.

## Configuration precedence

From highest to lowest priority, WireLoft uses:

1. values passed directly to the settings model internally;
2. process environment variables (usually prepended with `WL_*`);
3. the dotenv file;
4. `config.yml`;
5. file-secret settings;
6. application defaults.

An environment override therefore wins over a value saved in the Settings UI or written manually to `config.yml`.

The Settings screen writes to the same `config.yml` file. It only inserts or updates settings that were actually changed; it does not fill the file with every default.

## YAML and environment naming

YAML uses camelCase field aliases. Environment variables use uppercase snake case, with `WL_` as the prefix and a double underscore between nested objects.

For example:

```yaml
downloadSettings:
  maxConcurrentDownloads: 3
```

is equivalent to:

```text
WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS=3
```

## Configuration source locations

These two environment variables select the files WireLoft reads. They are **loader options**, not keys within `config.yml` itself.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WL_CONFIG_FILE` | `<project>/config/config.yml` | Select a different YAML configuration file. `~` is expanded. |
| `WL_ENV_FILE` | `<project>/.env` | Select a different dotenv file. |

The supplied Docker image seeds its default `config.yml` only once, when that file does not exist. It overrides the application fallback for two paths so persistent container storage is used:

```yaml
crypto:
  defaultSecretFile: /config/wl_secret.key

downloadSettings:
  downloadRoot: /downloads
  filenameRestrictionMode: windows
```

Where the Docker-seeded value differs from the model fallback, both are called out below.

---

## General

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `databasePath` | `WL_DATABASE_PATH` | `<project>/config/wireloft.db` | Path to the SQLite database. WireLoft derives `databaseUrl` from this value. |
| `logLevel` | `WL_LOG_LEVEL` | `INFO` | Application logging level. Allowed values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Input is normalized to uppercase. |
| `timezone` | **`TZ`** | `UTC` | Application timezone used by date/time-aware behavior and scheduling. Must be a valid [IANA]([IANA](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List)) zone such as `Europe/Amsterdam`. |

## Cryptography and application secret

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `crypto.secretKey` | `WL_CRYPTO__SECRET_KEY` | unset | Literal secret-key material. Accepts base64 or raw text suitable for WireLoft's Fernet key handling. Prefer a file/secret mechanism rather than putting sensitive key material in a committed YAML file. |
| `crypto.secretKeyFile` | `WL_CRYPTO__SECRET_KEY_FILE` | unset | Explicit path to a file containing the secret key. Cannot be an empty path. |
| `crypto.defaultSecretFile` | `WL_CRYPTO__DEFAULT_SECRET_FILE` | App fallback: `<project>/data/wl_secret.key`; Docker seed: `/config/wl_secret.key` | Fallback file WireLoft uses when neither a literal key nor explicit key file is configured. Keep this on persistent storage. |

The Docker default deliberately places the generated key under `/config` so it survives container recreation.

---

## Administrator authentication and sessions

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `loginSession.ttlSeconds` | `WL_LOGIN_SESSION__TTL_SECONDS` | `2592000` (30 days) | Length of a WireLoft administrator login session. Minimum is 60 seconds. |
| `adminAuth.passwordHash` | `WL_ADMIN_AUTH__PASSWORD_HASH` | unset | Precomputed administrator password hash. A valid stored hash begins with `scrypt$`. |
| `adminAuth.password` | `WL_ADMIN_AUTH__PASSWORD` | unset | Plain administrator password input. WireLoft derives and hashes it at startup, then removes the plaintext field/environment value from its process state. Prefer this environment variable over storing plaintext in YAML. Values `false`, `0`, or blank disable plaintext password input. |

If no administrator password/hash is configured, local UI authentication is disabled. For any instance reachable through a reverse proxy or untrusted network, configure `WL_ADMIN_AUTH__PASSWORD`.

The RSS feed token system is separate from administrator sessions; see [[Podcast-RSS-Feeds]].

---

## Daily Wire API endpoints

These defaults point to Daily Wire's production services and normally should not be changed.

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `dwApi.middlewareApi` | `WL_DW_API__MIDDLEWARE_API` | `https://middleware-prod.dailywire.com/middleware` | Base URL for Daily Wire middleware API requests. Must be a complete HTTP(S) URL. |
| `dwApi.streamApi` | `WL_DW_API__STREAM_API` | `https://stream.media.dailywire.com` | Base URL for Daily Wire stream API requests. Must be a complete HTTP(S) URL. |

---

## Daily Wire OAuth

These settings describe the Daily Wire device/OAuth client used by WireLoft. They are advanced integration settings and normally should not be modified.

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `dwOauth.issuer` | `WL_DW_OAUTH__ISSUER` | `https://authorize.dailywire.com` | OAuth issuer URL. Must be a complete HTTP(S) URL. |
| `dwOauth.audience` | `WL_DW_OAUTH__AUDIENCE` | `https://api.dailywire.com/` | OAuth audience. Must be a complete HTTP(S) URL. |
| `dwOauth.clientId` | `WL_DW_OAUTH__CLIENT_ID` | `FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE` | OAuth client ID used by WireLoft's Daily Wire authorization flow. |
| `dwOauth.scope` | `WL_DW_OAUTH__SCOPE` | `openid profile offline_access` | OAuth scopes requested by WireLoft. |

---

## Daily Wire request throttling

These values control WireLoft's pacing of Daily Wire requests.

| `config.yml` key | Environment variable | Default              | What it does |
| --- | --- |----------------------| --- |
| `dwTimeout.minFastRequestMs` | `WL_DW_TIMEOUT__MIN_FAST_REQUEST_MS` | `100`                | Minimum spacing, in milliseconds, associated with fast requests. Must be 0 or greater. |
| `dwTimeout.maxFastRequests` | `WL_DW_TIMEOUT__MAX_FAST_REQUESTS` | `350`                | Maximum number of fast requests before the slower pacing rule applies. Must be at least 1. |
| `dwTimeout.minSlowRequestMs` | `WL_DW_TIMEOUT__MIN_SLOW_REQUEST_MS` | `120.000` (1 minute) | Slow-request wait value in milliseconds after the fast-request threshold. Must be 0 or greater. |

These are advanced safety/tuning settings. Raising request rates may increase the chance of remote throttling or unstable behavior.

---

## Movie metadata / TMDB

WireLoft can use TMDB to enrich movie metadata, including release dates used by movie output templates.

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `movieMetadata.tmdbReadAccessToken` | `WL_MOVIE_METADATA__TMDB_READ_ACCESS_TOKEN` | unset | TMDB API Read Access Token. Blank values are treated as unset. |
| `movieMetadata.tmdbApiBaseUrl` | `WL_MOVIE_METADATA__TMDB_API_BASE_URL` | `https://api.themoviedb.org/3` | TMDB API base URL. Must be a complete HTTP(S) URL. |
| `movieMetadata.language` | `WL_MOVIE_METADATA__LANGUAGE` | `en-US` | Language requested for TMDB metadata. |
| `movieMetadata.requestTimeoutSeconds` | `WL_MOVIE_METADATA__REQUEST_TIMEOUT_SECONDS` | `10.0` | Timeout for a TMDB API request. Minimum 1 second. |
| `movieMetadata.maxRetries` | `WL_MOVIE_METADATA__MAX_RETRIES` | `2` | Number of retries for transient TMDB failures. Allowed range: 0–5. |

---

## Scheduler

WireLoft's internal scheduler runs background jobs such as episode discovery and file verification.

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `scheduler.enabled` | `WL_SCHEDULER__ENABLED` | `true` | Enables the internal APScheduler-based scheduler. Disabling it stops scheduled background work. |
| `scheduler.maxWorkers` | `WL_SCHEDULER__MAX_WORKERS` | `5` | Maximum number of jobs that can execute concurrently in the scheduler's thread-pool executor. Minimum 1. |
| `scheduler.defaultMaxRetries` | `WL_SCHEDULER__DEFAULT_MAX_RETRIES` | `3` | Default maximum retry count when a task/schedule does not specify its own value. Minimum 0. |
| `scheduler.retryBackoffSeconds` | `WL_SCHEDULER__RETRY_BACKOFF_SECONDS` | `5.0` | Base delay used for exponential retry backoff. Minimum 0 seconds. |

See [[Automation-and-Background-Tasks]].

---

## New episode discovery and monitoring

All cron strings use standard five-field cron syntax (`minute hour day-of-month month day-of-week`).

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `newEpisodeSchedule.findEpisodesCron` | `WL_NEW_EPISODE_SCHEDULE__FIND_EPISODES_CRON` | `*/30 * * * *` | Searches managed shows for new episodes every 30 minutes by default. |
| `newEpisodeSchedule.monitorEpisodeCron` | `WL_NEW_EPISODE_SCHEDULE__MONITOR_EPISODE_CRON` | `*/1 * * * *` | Rechecks episodes that exist but are not yet considered fully published every minute by default. |
| `newEpisodeSchedule.checkNoShowTodayCron` | `WL_NEW_EPISODE_SCHEDULE__CHECK_NO_SHOW_TODAY_CRON` | `0 */6 * * *` | Rechecks Daily Wire `No Show Today` placeholder state every six hours by default. |
| `newEpisodeSchedule.metadataRefreshIntervals` | `WL_NEW_EPISODE_SCHEDULE__METADATA_REFRESH_INTERVALS` | `5m,15m,30m,1h,3h,6h,24h` | Offsets after publication at which finalized episode metadata is refreshed. Values must be positive `s`, `m`, `h`, or `d` tokens, comma-separated, unique, and strictly increasing. |


---

## Episode publication timing

Daily Wire can report an episode as published before the media has fully transitioned away from a live/countdown version. WireLoft uses two timing thresholds.

| `config.yml` key | Environment variable | Default | What it does                                                                                                                                                                                                                                                                     |
| --- | --- | --- |----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `episodeStatusTiming.publishedCountdownAfterMinutes` | `WL_EPISODE_STATUS_TIMING__PUBLISHED_COUNTDOWN_AFTER_MINUTES` | `20` | Safety fallback: usually WireLoft can very accurately determine episode status. If something seems to be hanging, this is the fallback. Minutes after Daily Wire reports publication before WireLoft may treat the episode as being in the published/countdown stage. Minimum 0. |
| `episodeStatusTiming.publishedFinalAfterMinutes` | `WL_EPISODE_STATUS_TIMING__PUBLISHED_FINAL_AFTER_MINUTES` | `180` | Safety fallback: usually WireLoft can very accurately determine episode status. If something seems to be hanging, this is the fallback. Minutes after publication before WireLoft can safely treat the episode as final/past the countdown stage. Must be at least the countdown threshold.                                                                                                                              |

These settings are all safety fallbacks, mostly originating from a time when The Daily Wire's API did not provide any useful information about episode publish status.
It still doesnt, really, but it does expose when an episode is eligible to be downloaded (on The Daily Wire website itself), which happens to be true only if the episode
is fully published. WireLoft now uses this and its very reliable. As its still a workaround though, these settings provide a fallback for if for example The Daily Wire
ever decides to stop supporting downloads ect.


---

## Downloads

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `downloadSettings.verifyDownloadsCron` | `WL_DOWNLOAD_SETTINGS__VERIFY_DOWNLOADS_CRON` | `0 */2 * * *` | Schedule for the download-verification task; every two hours by default. |
| `downloadSettings.maxConcurrentDownloads` | `WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS` | `5` | Maximum downloads allowed at once. Minimum 1. |
| `downloadSettings.maxDownloadAttempts` | `WL_DOWNLOAD_SETTINGS__MAX_DOWNLOAD_ATTEMPTS` | `3` | Maximum attempts for a media download. Minimum 1. |
| `downloadSettings.downloadTimeoutSeconds` | `WL_DOWNLOAD_SETTINGS__DOWNLOAD_TIMEOUT_SECONDS` | `600` | Timeout for each individual download attempt. Minimum 1 second. |
| `downloadSettings.downloadRoot` | `WL_DOWNLOAD_SETTINGS__DOWNLOAD_ROOT` | App fallback: `<project>/downloads`; Docker seed: `/downloads` | Physical directory to which the `/downloads/` prefix in Local Media Profile templates maps. |
| `downloadSettings.filenameRestrictionMode` | `WL_DOWNLOAD_SETTINGS__FILENAME_RESTRICTION_MODE` | `windows` | Filename sanitization mode. Allowed: `unrestricted`, `windows`, `restricted`. See [[Local-Media-Profiles#filename-restrictions]]. |
| `downloadSettings.remuxVideoToMp4` | `WL_DOWNLOAD_SETTINGS__REMUX_VIDEO_TO_MP4` | `true` | Repackages downloaded HLS video into MP4 rather than leaving raw TS. This is a fast, lossless container change—not a video re-encode—and requires FFmpeg. |
| `downloadSettings.ffmpegPath` | `WL_DOWNLOAD_SETTINGS__FFMPEG_PATH` | `ffmpeg` | FFmpeg executable/path used for MP4 remuxing. Must be non-empty. |

### Filename modes

- `unrestricted` preserves Unicode and normal punctuation while still preventing path-breaking characters.
- `windows` keeps Unicode but removes characters/reserved names Windows cannot safely use. This is the default.
- `restricted` produces conservative ASCII-only components using letters, digits, `.`, `_`, and `-`.

See [[Local-Media-Profiles]] for exact behavior.

---

## File watcher

The file watcher reconciles download records with what actually exists on disk.

| `config.yml` key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `fileWatcher.enabled` | `WL_FILE_WATCHER__ENABLED` | `true` | Enables periodic checks that keep downloaded-file state synchronized with the database. |
| `fileWatcher.scanCron` | `WL_FILE_WATCHER__SCAN_CRON` | `*/10 * * * *` | Schedule for the periodic file scan; every 10 minutes by default. |
| `fileWatcher.verifyFileSize` | `WL_FILE_WATCHER__VERIFY_FILE_SIZE` | `true` | Treats a download as corrupted when its file is empty or smaller than the size recorded when downloading completed. |

The watcher is intended to detect missing/corrupted media, not to infer arbitrary manual file moves or renames. If you reorganize downloaded files outside WireLoft, its recorded file path can stop matching disk state.

---

## Complete example

You only need to include values you want to override. A realistic custom `config.yml` might be:

```yaml
logLevel: INFO

movieMetadata:
  language: en-US

scheduler:
  maxWorkers: 4

newEpisodeSchedule:
  findEpisodesCron: "*/15 * * * *"
  metadataRefreshIntervals: 5m,15m,30m,1h,3h,6h,24h

episodeStatusTiming:
  publishedCountdownAfterMinutes: 20
  publishedFinalAfterMinutes: 180

downloadSettings:
  downloadRoot: /downloads
  maxConcurrentDownloads: 3
  filenameRestrictionMode: windows
  remuxVideoToMp4: true

fileWatcher:
  enabled: true
  scanCron: "*/10 * * * *"
  verifyFileSize: true
```

An environment variable can override any of those fields without editing the YAML. For example:

```yaml
environment:
  - TZ=Europe/Amsterdam
  - WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS=2
  - WL_FILE_WATCHER__SCAN_CRON=*/20 * * * *
```