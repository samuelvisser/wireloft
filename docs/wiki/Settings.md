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

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>databasePath</code></td>
<td><code>WL_DATABASE_PATH</code></td>
<td><code>&lt;project&gt;/config/wireloft.db</code></td>
</tr>
<tr>
<td colspan="3">Path to the SQLite database. WireLoft derives <code>databaseUrl</code> from this value.</td>
</tr>
<tr>
<td><code>logLevel</code></td>
<td><code>WL_LOG_LEVEL</code></td>
<td><code>INFO</code></td>
</tr>
<tr>
<td colspan="3">Application logging level. Allowed values: <code>DEBUG</code>, <code>INFO</code>, <code>WARNING</code>, <code>ERROR</code>, <code>CRITICAL</code>. Input is normalized to uppercase.</td>
</tr>
<tr>
<td><code>timezone</code></td>
<td><strong><code>TZ</code></strong></td>
<td><code>UTC</code></td>
</tr>
<tr>
<td colspan="3">Application timezone used by date/time-aware behavior and scheduling. Must be a valid <a href="https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List">IANA</a> zone such as <code>Europe/Amsterdam</code>.</td>
</tr>
</tbody>
</table>

## Cryptography and application secret

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>crypto.secretKey</code></td>
<td><code>WL_CRYPTO__SECRET_KEY</code></td>
<td>unset</td>
</tr>
<tr>
<td colspan="3">Literal secret-key material. Accepts base64 or raw text suitable for WireLoft's Fernet key handling. Prefer a file/secret mechanism rather than putting sensitive key material in a committed YAML file.</td>
</tr>
<tr>
<td><code>crypto.secretKeyFile</code></td>
<td><code>WL_CRYPTO__SECRET_KEY_FILE</code></td>
<td>unset</td>
</tr>
<tr>
<td colspan="3">Explicit path to a file containing the secret key. Cannot be an empty path.</td>
</tr>
<tr>
<td><code>crypto.defaultSecretFile</code></td>
<td><code>WL_CRYPTO__DEFAULT_SECRET_FILE</code></td>
<td>App fallback: <code>&lt;project&gt;/data/wl_secret.key</code>; Docker seed: <code>/config/wl_secret.key</code></td>
</tr>
<tr>
<td colspan="3">Fallback file WireLoft uses when neither a literal key nor explicit key file is configured. Keep this on persistent storage.</td>
</tr>
</tbody>
</table>

The Docker default deliberately places the generated key under `/config` so it survives container recreation.

---

## Administrator authentication and sessions

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>loginSession.ttlSeconds</code></td>
<td><code>WL_LOGIN_SESSION__TTL_SECONDS</code></td>
<td><code>2592000</code> (30 days)</td>
</tr>
<tr>
<td colspan="3">Length of a WireLoft administrator login session. Minimum is 60 seconds.</td>
</tr>
<tr>
<td><code>adminAuth.passwordHash</code></td>
<td><code>WL_ADMIN_AUTH__PASSWORD_HASH</code></td>
<td>unset</td>
</tr>
<tr>
<td colspan="3">Precomputed administrator password hash. A valid stored hash begins with <code>scrypt$</code>.</td>
</tr>
<tr>
<td><code>adminAuth.password</code></td>
<td><code>WL_ADMIN_AUTH__PASSWORD</code></td>
<td>unset</td>
</tr>
<tr>
<td colspan="3">Plain administrator password input. WireLoft derives and hashes it at startup, then removes the plaintext field/environment value from its process state. Prefer this environment variable over storing plaintext in YAML. Values <code>false</code>, <code>0</code>, or blank disable plaintext password input.</td>
</tr>
</tbody>
</table>

If no administrator password/hash is configured, local UI authentication is disabled. For any instance reachable through a reverse proxy or untrusted network, configure `WL_ADMIN_AUTH__PASSWORD`.

The RSS feed token system is separate from administrator sessions; see [[Podcast-RSS-Feeds]].

---

## Daily Wire API endpoints

These defaults point to Daily Wire's production services and normally should not be changed.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>dwApi.middlewareApi</code></td>
<td><code>WL_DW_API__MIDDLEWARE_API</code></td>
<td><code>https://middleware-prod.dailywire.com/middleware</code></td>
</tr>
<tr>
<td colspan="3">Base URL for Daily Wire middleware API requests. Must be a complete HTTP(S) URL.</td>
</tr>
<tr>
<td><code>dwApi.streamApi</code></td>
<td><code>WL_DW_API__STREAM_API</code></td>
<td><code>https://stream.media.dailywire.com</code></td>
</tr>
<tr>
<td colspan="3">Base URL for Daily Wire stream API requests. Must be a complete HTTP(S) URL.</td>
</tr>
</tbody>
</table>

---

## Daily Wire OAuth

These settings describe the Daily Wire device/OAuth client used by WireLoft. They are advanced integration settings and normally should not be modified.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>dwOauth.issuer</code></td>
<td><code>WL_DW_OAUTH__ISSUER</code></td>
<td><code>https://authorize.dailywire.com</code></td>
</tr>
<tr>
<td colspan="3">OAuth issuer URL. Must be a complete HTTP(S) URL.</td>
</tr>
<tr>
<td><code>dwOauth.audience</code></td>
<td><code>WL_DW_OAUTH__AUDIENCE</code></td>
<td><code>https://api.dailywire.com/</code></td>
</tr>
<tr>
<td colspan="3">OAuth audience. Must be a complete HTTP(S) URL.</td>
</tr>
<tr>
<td><code>dwOauth.clientId</code></td>
<td><code>WL_DW_OAUTH__CLIENT_ID</code></td>
<td><code>FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE</code></td>
</tr>
<tr>
<td colspan="3">OAuth client ID used by WireLoft's Daily Wire authorization flow.</td>
</tr>
<tr>
<td><code>dwOauth.scope</code></td>
<td><code>WL_DW_OAUTH__SCOPE</code></td>
<td><code>openid profile offline_access</code></td>
</tr>
<tr>
<td colspan="3">OAuth scopes requested by WireLoft.</td>
</tr>
</tbody>
</table>

---

## Daily Wire request throttling

These values control WireLoft's pacing of Daily Wire requests.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>dwTimeout.minFastRequestMs</code></td>
<td><code>WL_DW_TIMEOUT__MIN_FAST_REQUEST_MS</code></td>
<td><code>100</code></td>
</tr>
<tr>
<td colspan="3">Minimum spacing, in milliseconds, associated with fast requests. Must be 0 or greater.</td>
</tr>
<tr>
<td><code>dwTimeout.maxFastRequests</code></td>
<td><code>WL_DW_TIMEOUT__MAX_FAST_REQUESTS</code></td>
<td><code>350</code></td>
</tr>
<tr>
<td colspan="3">Maximum number of fast requests before the slower pacing rule applies. Must be at least 1.</td>
</tr>
<tr>
<td><code>dwTimeout.minSlowRequestMs</code></td>
<td><code>WL_DW_TIMEOUT__MIN_SLOW_REQUEST_MS</code></td>
<td><code>120.000</code> (2 minutes)</td>
</tr>
<tr>
<td colspan="3">Slow-request wait value in milliseconds after the fast-request threshold. Must be 0 or greater.</td>
</tr>
</tbody>
</table>

These are advanced safety/tuning settings. Raising request rates may increase the chance of remote throttling or unstable behavior.

---

## Movie metadata / TMDB

WireLoft can use TMDB to enrich movie metadata, including release dates used by movie output templates.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>movieMetadata.tmdbReadAccessToken</code></td>
<td><code>WL_MOVIE_METADATA__TMDB_READ_ACCESS_TOKEN</code></td>
<td>unset</td>
</tr>
<tr>
<td colspan="3">TMDB API Read Access Token. Blank values are treated as unset.</td>
</tr>
<tr>
<td><code>movieMetadata.tmdbApiBaseUrl</code></td>
<td><code>WL_MOVIE_METADATA__TMDB_API_BASE_URL</code></td>
<td><code>https://api.themoviedb.org/3</code></td>
</tr>
<tr>
<td colspan="3">TMDB API base URL. Must be a complete HTTP(S) URL.</td>
</tr>
<tr>
<td><code>movieMetadata.language</code></td>
<td><code>WL_MOVIE_METADATA__LANGUAGE</code></td>
<td><code>en-US</code></td>
</tr>
<tr>
<td colspan="3">Language requested for TMDB metadata.</td>
</tr>
<tr>
<td><code>movieMetadata.requestTimeoutSeconds</code></td>
<td><code>WL_MOVIE_METADATA__REQUEST_TIMEOUT_SECONDS</code></td>
<td><code>10.0</code></td>
</tr>
<tr>
<td colspan="3">Timeout for a TMDB API request. Minimum 1 second.</td>
</tr>
<tr>
<td><code>movieMetadata.maxRetries</code></td>
<td><code>WL_MOVIE_METADATA__MAX_RETRIES</code></td>
<td><code>2</code></td>
</tr>
<tr>
<td colspan="3">Number of retries for transient TMDB failures. Allowed range: 0–5.</td>
</tr>
</tbody>
</table>

---

## Scheduler

WireLoft's internal scheduler runs background jobs such as episode discovery and file verification.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>scheduler.enabled</code></td>
<td><code>WL_SCHEDULER__ENABLED</code></td>
<td><code>true</code></td>
</tr>
<tr>
<td colspan="3">Enables the internal APScheduler-based scheduler. Disabling it stops scheduled background work.</td>
</tr>
<tr>
<td><code>scheduler.maxWorkers</code></td>
<td><code>WL_SCHEDULER__MAX_WORKERS</code></td>
<td><code>5</code></td>
</tr>
<tr>
<td colspan="3">Maximum number of jobs that can execute concurrently in the scheduler's thread-pool executor. Minimum 1.</td>
</tr>
<tr>
<td><code>scheduler.defaultMaxRetries</code></td>
<td><code>WL_SCHEDULER__DEFAULT_MAX_RETRIES</code></td>
<td><code>3</code></td>
</tr>
<tr>
<td colspan="3">Default maximum retry count when a task/schedule does not specify its own value. Minimum 0.</td>
</tr>
<tr>
<td><code>scheduler.retryBackoffSeconds</code></td>
<td><code>WL_SCHEDULER__RETRY_BACKOFF_SECONDS</code></td>
<td><code>5.0</code></td>
</tr>
<tr>
<td colspan="3">Base delay used for exponential retry backoff. Minimum 0 seconds.</td>
</tr>
</tbody>
</table>

See [[Automation-and-Background-Tasks]].

---

## New episode discovery and monitoring

All cron strings use standard five-field cron syntax (`minute hour day-of-month month day-of-week`).

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>newEpisodeSchedule.findEpisodesCron</code></td>
<td><code>WL_NEW_EPISODE_SCHEDULE__FIND_EPISODES_CRON</code></td>
<td><code>*/30 * * * *</code></td>
</tr>
<tr>
<td colspan="3">Searches managed shows for new episodes every 30 minutes by default.</td>
</tr>
<tr>
<td><code>newEpisodeSchedule.monitorEpisodeCron</code></td>
<td><code>WL_NEW_EPISODE_SCHEDULE__MONITOR_EPISODE_CRON</code></td>
<td><code>*/2 * * * *</code></td>
</tr>
<tr>
<td colspan="3">Rechecks episodes that exist but are not yet considered fully published every two minutes by default.</td>
</tr>
<tr>
<td><code>newEpisodeSchedule.checkEpisodesStuckAtDwProcessingCron</code></td>
<td><code>WL_NEW_EPISODE_SCHEDULE__CHECK_EPISODES_STUCK_AT_DW_PROCESSING_CRON</code></td>
<td><code>0 * * * *</code></td>
</tr>
<tr>
<td colspan="3">Checks <code>dw_processing</code> episodes once per hour by default and cleans up persistent <code>No Show Today</code> placeholders or continuously missing Daily Wire episodes after the configured deletion delay.</td>
</tr>
<tr>
<td><code>newEpisodeSchedule.metadataRefreshIntervals</code></td>
<td><code>WL_NEW_EPISODE_SCHEDULE__METADATA_REFRESH_INTERVALS</code></td>
<td><code>15m,30m,1h,3h,6h,24h,3d</code></td>
</tr>
<tr>
<td colspan="3">Offsets after publication at which finalized episode metadata is refreshed. Values must be positive <code>s</code>, <code>m</code>, <code>h</code>, or <code>d</code> tokens, comma-separated, unique, and strictly increasing.</td>
</tr>
</tbody>
</table>


---

## Episode lifecycle timing

Daily Wire can report an episode as published before the media has fully transitioned away from a live/countdown version, and it can temporarily leave unusable entries in <code>dw_processing</code>. WireLoft uses these timing thresholds to handle both cases.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>episodeStatusTiming.publishedCountdownAfterMinutes</code></td>
<td><code>WL_EPISODE_STATUS_TIMING__PUBLISHED_COUNTDOWN_AFTER_MINUTES</code></td>
<td><code>20</code></td>
</tr>
<tr>
<td colspan="3">Safety fallback: usually WireLoft can very accurately determine episode status. If something seems to be hanging, this is the fallback. Minutes after Daily Wire reports publication before WireLoft may treat the episode as being in the published/countdown stage. Minimum 0.</td>
</tr>
<tr>
<td><code>episodeStatusTiming.publishedFinalAfterMinutes</code></td>
<td><code>WL_EPISODE_STATUS_TIMING__PUBLISHED_FINAL_AFTER_MINUTES</code></td>
<td><code>180</code></td>
</tr>
<tr>
<td colspan="3">Safety fallback: usually WireLoft can very accurately determine episode status. If something seems to be hanging, this is the fallback. Minutes after publication before WireLoft can safely treat the episode as final/past the countdown stage. Must be at least the countdown threshold.</td>
</tr>
<tr>
<td><code>episodeStatusTiming.dwProcessingDeleteAfterMinutes</code></td>
<td><code>WL_EPISODE_STATUS_TIMING__DW_PROCESSING_DELETE_AFTER_MINUTES</code></td>
<td><code>240</code> (4 hours)</td>
</tr>
<tr>
<td colspan="3">How long an unusable <code>dw_processing</code> episode must remain in the same placeholder/404 incident before automatic cleanup may delete it. Both the episode and the processing incident must be at least this old. Set to <code>0</code> to make the episode eligible on the next cleanup run. The episode Actions menu can use <strong>Early Delete</strong> to bypass this delay for one processing episode.</td>
</tr>
</tbody>
</table>

The countdown and final thresholds are safety fallbacks, mostly originating from a time when The Daily Wire's API did not provide useful information about episode publish status. WireLoft now also uses the separate processing-deletion delay to avoid destroying an episode during a transient Daily Wire 404 or placeholder state.


---

## Downloads

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>downloadSettings.verifyDownloadsCron</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__VERIFY_DOWNLOADS_CRON</code></td>
<td><code>0 */2 * * *</code></td>
</tr>
<tr>
<td colspan="3">Schedule for the download-verification task; every two hours by default.</td>
</tr>
<tr>
<td><code>downloadSettings.maxConcurrentDownloads</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS</code></td>
<td><code>5</code></td>
</tr>
<tr>
<td colspan="3">Maximum downloads allowed at once. Minimum 1.</td>
</tr>
<tr>
<td><code>downloadSettings.maxDownloadAttempts</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__MAX_DOWNLOAD_ATTEMPTS</code></td>
<td><code>3</code></td>
</tr>
<tr>
<td colspan="3">Maximum attempts for a media download. Minimum 1.</td>
</tr>
<tr>
<td><code>downloadSettings.downloadTimeoutSeconds</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__DOWNLOAD_TIMEOUT_SECONDS</code></td>
<td><code>600</code></td>
</tr>
<tr>
<td colspan="3">Timeout for each individual download attempt. Minimum 1 second.</td>
</tr>
<tr>
<td><code>downloadSettings.downloadRoot</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__DOWNLOAD_ROOT</code></td>
<td>App fallback: <code>&lt;project&gt;/downloads</code>; Docker seed: <code>/downloads</code></td>
</tr>
<tr>
<td colspan="3">Physical directory to which the <code>/downloads/</code> prefix in Local Media Profile templates maps.</td>
</tr>
<tr>
<td><code>downloadSettings.filenameRestrictionMode</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__FILENAME_RESTRICTION_MODE</code></td>
<td><code>windows</code></td>
</tr>
<tr>
<td colspan="3">Filename sanitization mode. Allowed: <code>unrestricted</code>, <code>windows</code>, <code>restricted</code>. See <a href="Local-Media-Profiles#filename-restrictions">Local-Media-Profiles#filename-restrictions</a>.</td>
</tr>
<tr>
<td><code>downloadSettings.remuxVideoToMp4</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__REMUX_VIDEO_TO_MP4</code></td>
<td><code>true</code></td>
</tr>
<tr>
<td colspan="3">Repackages downloaded HLS video into MP4 rather than leaving raw TS. This is a fast, lossless container change—not a video re-encode—and requires FFmpeg.</td>
</tr>
<tr>
<td><code>downloadSettings.ffmpegPath</code></td>
<td><code>WL_DOWNLOAD_SETTINGS__FFMPEG_PATH</code></td>
<td><code>ffmpeg</code></td>
</tr>
<tr>
<td colspan="3">FFmpeg executable/path used for MP4 remuxing. Must be non-empty.</td>
</tr>
</tbody>
</table>

### Filename modes

- `unrestricted` preserves Unicode and normal punctuation while still preventing path-breaking characters.
- `windows` keeps Unicode but removes characters/reserved names Windows cannot safely use. This is the default.
- `restricted` produces conservative ASCII-only components using letters, digits, `.`, `_`, and `-`.

See [[Local-Media-Profiles]] for exact behavior.

---

## File watcher

The file watcher reconciles download records with what actually exists on disk.

<table>
<thead>
<tr>
<th><code>config.yml</code> key</th>
<th>Environment variable</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>fileWatcher.enabled</code></td>
<td><code>WL_FILE_WATCHER__ENABLED</code></td>
<td><code>true</code></td>
</tr>
<tr>
<td colspan="3">Enables periodic checks that keep downloaded-file state synchronized with the database.</td>
</tr>
<tr>
<td><code>fileWatcher.scanCron</code></td>
<td><code>WL_FILE_WATCHER__SCAN_CRON</code></td>
<td><code>*/10 * * * *</code></td>
</tr>
<tr>
<td colspan="3">Schedule for the periodic file scan; every 10 minutes by default.</td>
</tr>
<tr>
<td><code>fileWatcher.verifyFileSize</code></td>
<td><code>WL_FILE_WATCHER__VERIFY_FILE_SIZE</code></td>
<td><code>true</code></td>
</tr>
<tr>
<td colspan="3">Treats a download as corrupted when its file is empty or smaller than the size recorded when downloading completed.</td>
</tr>
</tbody>
</table>

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
  metadataRefreshIntervals: 15m,30m,1h,3h,6h,24h,3d

episodeStatusTiming:
  publishedCountdownAfterMinutes: 20
  publishedFinalAfterMinutes: 180
  dwProcessingDeleteAfterMinutes: 240

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