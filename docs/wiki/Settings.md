# Settings

Most WireLoft configuration can be changed from the **Settings** page. The interface groups normal options into General, Downloads, Automation, DailyWire, and Advanced tabs and explains environment-variable overrides when they are active.

This page is the complete 1.1 reference for settings users may need to configure.

## Where settings are stored

Changes made in the Settings page are saved to `config.yml`. WireLoft keeps that file sparse: settings you never change do not need to be written there and continue using their built-in defaults.

In the Docker image, `config.yml` lives under the persistent `/config` mount.

### Environment variables

Environment variables override values from `config.yml`. This is useful when your Compose file or deployment platform should enforce a value.

A nested YAML setting such as:

```yaml
downloadSettings:
  maxConcurrentDownloads: 3
```

can be overridden with:

```text
WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS=3
```

The Settings page identifies environment-controlled values and tells you why you cannot change them in the UI.

### Practical precedence

For normal installations, think of precedence as:

1. environment variables;
2. `config.yml` / Settings UI;
3. built-in defaults.

WireLoft also supports a `.env` file and file-secret settings for advanced deployments. Environment values still take priority over those lower-level sources.

`TZ` is the special environment variable used for the application timezone.

## Configuration file locations

These environment variables choose the configuration source files themselves:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WL_CONFIG_FILE` | `<project>/config/config.yml` | Use a different YAML settings file. |
| `WL_ENV_FILE` | `<project>/.env` | Use a different dotenv file. |

They are deployment options, not keys inside `config.yml`.

---

## General

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `databasePath` | `WL_DATABASE_PATH` | `<project>/config/wireloft.db` | Location of the SQLite database. The Docker image sets this to `/config/wireloft.db`. |
| `logLevel` | `WL_LOG_LEVEL` | `INFO` | Logging detail: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `timezone` | `TZ` | `UTC` | Timezone used for schedules and displayed time-sensitive behavior. Use an [IANA](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List) value such as `Europe/Amsterdam`. |
| `loginSession.ttlSeconds` | `WL_LOGIN_SESSION__TTL_SECONDS` | `2592000` (30 days) | How long a signed-in browser remains authenticated. |

### Administrator password

Administrator authentication is normally configured as a deployment environment variable:

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `adminAuth.password` | `WL_ADMIN_AUTH__PASSWORD` | unset | Plain password input used when WireLoft starts. Recommended way to enable the UI login in Docker. |
| `adminAuth.passwordHash` | `WL_ADMIN_AUTH__PASSWORD_HASH` | unset | Advanced option for supplying a pre-generated WireLoft password hash. |

If neither is configured, the WireLoft administrator login is disabled. See [[Security-and-Remote-Access]].

---

## Downloads

These settings are available under **Settings → Downloads**.

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `downloadSettings.downloadRoot` | `WL_DOWNLOAD_SETTINGS__DOWNLOAD_ROOT` | `<project>/downloads` | Root directory used for paths beginning with `/downloads/`. In the supplied Docker layout, set/use `/downloads` to target the mounted media volume. |
| `downloadSettings.downloadMode` | `WL_DOWNLOAD_SETTINGS__DOWNLOAD_MODE` | `direct` | System default: `direct` or `temporary`. Local Media Profiles can inherit or override it. |
| `downloadSettings.temporaryDownloadRoot` | `WL_DOWNLOAD_SETTINGS__TEMPORARY_DOWNLOAD_ROOT` | `<project>/downloads/.wireloft-temp` | Staging directory used by temporary download mode. It may be on different storage from the final library. |
| `downloadSettings.rssCacheRoot` | `WL_DOWNLOAD_SETTINGS__RSS_CACHE_ROOT` | `/downloads/.wireloft-rss-cache` | Root for media cached while fulfilling RSS requests. It may point to mounted storage or container-local storage such as `/tmp/wireloft-rss-cache`. |
| `downloadSettings.maxConcurrentDownloads` | `WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS` | `5` | Maximum downloads running at once. |
| `downloadSettings.maxDownloadAttempts` | `WL_DOWNLOAD_SETTINGS__MAX_DOWNLOAD_ATTEMPTS` | `3` | Automatic attempts before a download is left failed. |
| `downloadSettings.downloadTimeoutSeconds` | `WL_DOWNLOAD_SETTINGS__DOWNLOAD_TIMEOUT_SECONDS` | `600` | Timeout for one download attempt. |
| `downloadSettings.filenameRestrictionMode` | `WL_DOWNLOAD_SETTINGS__FILENAME_RESTRICTION_MODE` | `windows` | Filename compatibility: `unrestricted`, `windows`, or `restricted`. |
| `downloadSettings.remuxVideoToMp4` | `WL_DOWNLOAD_SETTINGS__REMUX_VIDEO_TO_MP4` | `true` | Repackage compatible downloaded video into MP4 without re-encoding. |
| `downloadSettings.ffmpegPath` | `WL_DOWNLOAD_SETTINGS__FFMPEG_PATH` | `ffmpeg` | FFmpeg executable used for MP4 remuxing. |
| `downloadSettings.verifyDownloadsCron` | `WL_DOWNLOAD_SETTINGS__VERIFY_DOWNLOADS_CRON` | `0 */2 * * *` | Schedule for periodic download verification; every two hours by default. |

### Direct versus temporary mode

**Direct** is the simple default. **Temporary** keeps incomplete download/processing work in the temporary folder and publishes the completed media into the final library at the end.

Temporary mode is useful when a media server watches the destination and should never see partial files. See [[Downloads-and-File-Integrity]] and [[Local-Media-Profiles]].

### Filename modes

- `unrestricted` — preserves most Unicode and punctuation while preventing path-breaking values.
- `windows` — keeps Unicode but removes Windows-incompatible characters and names. This is the default.
- `restricted` — conservative ASCII-style filenames.

---

## File watcher

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `fileWatcher.enabled` | `WL_FILE_WATCHER__ENABLED` | `true` | Periodically checks tracked completed files. |
| `fileWatcher.scanCron` | `WL_FILE_WATCHER__SCAN_CRON` | `*/10 * * * *` | File watcher schedule; every ten minutes by default. |
| `fileWatcher.verifyFileSize` | `WL_FILE_WATCHER__VERIFY_FILE_SIZE` | `true` | Marks an empty or unexpectedly smaller completed file as corrupted. |

The watcher tracks files WireLoft already knows about; it is not intended to index arbitrary files across your entire media library.

---

## Automation

These settings are available under **Settings → Automation**.

### Scheduler

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `scheduler.enabled` | `WL_SCHEDULER__ENABLED` | `true` | Enables automatic indexing, monitoring and scheduled work. |
| `scheduler.maxWorkers` | `WL_SCHEDULER__MAX_WORKERS` | `15` | Maximum general background tasks that may run in parallel. Download concurrency is controlled separately. |
| `scheduler.stalledTaskTimeoutMinutes` | `WL_SCHEDULER__STALLED_TASK_TIMEOUT_MINUTES` | `20` | Cancels work whose progress has not changed for this long. |
| `scheduler.defaultMaxRetries` | `WL_SCHEDULER__DEFAULT_MAX_RETRIES` | `3` | Default retry count for eligible background tasks. |
| `scheduler.retryBackoffSeconds` | `WL_SCHEDULER__RETRY_BACKOFF_SECONDS` | `5` | Base delay used when spacing automatic retries. |

### Episode discovery and monitoring

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `newEpisodeSchedule.findEpisodesCron` | `WL_NEW_EPISODE_SCHEDULE__FIND_EPISODES_CRON` | `*/30 * * * *` | Checks managed shows for new episodes every 30 minutes. |
| `newEpisodeSchedule.monitorPendingEpisodeCron` | `WL_NEW_EPISODE_SCHEDULE__MONITOR_PENDING_EPISODE_CRON` | `*/2 * * * *` | Rechecks known episodes that are scheduled, live, processing, or otherwise not final. |
| `newEpisodeSchedule.monitorNoUsableMediaEpisodeCron` | `WL_NEW_EPISODE_SCHEDULE__MONITOR_NO_USABLE_MEDIA_EPISODE_CRON` | `*/20 * * * *` | Rechecks episodes that temporarily have no usable Daily Wire media. |
| `newEpisodeSchedule.metadataRefreshIntervals` | `WL_NEW_EPISODE_SCHEDULE__METADATA_REFRESH_INTERVALS` | `15m,30m,1h,3h,6h,24h,3d` | Follow-up metadata refreshes after publication. |

Metadata intervals accept positive values using `s`, `m`, `h`, or `d`, separated by commas and ordered from shortest to longest.

### Episode lifecycle safeguards

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `episodeStatusTiming.publishedFinalAfterMinutes` | `WL_EPISODE_STATUS_TIMING__PUBLISHED_FINAL_AFTER_MINUTES` | `180` | Safety threshold for an episode that remains stuck on a countdown-style published version. |
| `episodeStatusTiming.dwProcessingMaxMinutes` | `WL_EPISODE_STATUS_TIMING__DW_PROCESSING_MAX_MINUTES` | `60` | Maximum time an episode may remain in Daily Wire processing before WireLoft treats its media as unavailable. |
| `episodeStatusTiming.noUsableMediaDeleteAfterMinutes` | `WL_EPISODE_STATUS_TIMING__NO_USABLE_MEDIA_DELETE_AFTER_MINUTES` | `240` | Waiting period before a persistently unavailable episode may be cleaned up. |

These are safeguards for unusual Daily Wire publication states. Most users should leave them at their defaults. See [[Automation-and-Background-Tasks]].

---

## Daily Wire integration

The DailyWire tab contains the account connection plus advanced integration settings. Ordinary installations should leave the endpoint, OAuth, and pacing values unchanged.

### API endpoints

| Setting | Environment variable | Default |
| --- | --- | --- |
| `dwApi.middlewareApi` | `WL_DW_API__MIDDLEWARE_API` | `https://middleware-prod.dailywire.com/middleware` |
| `dwApi.streamApi` | `WL_DW_API__STREAM_API` | `https://stream.media.dailywire.com` |

### OAuth client

| Setting | Environment variable | Default |
| --- | --- | --- |
| `dwOauth.issuer` | `WL_DW_OAUTH__ISSUER` | `https://authorize.dailywire.com` |
| `dwOauth.audience` | `WL_DW_OAUTH__AUDIENCE` | `https://api.dailywire.com/` |
| `dwOauth.clientId` | `WL_DW_OAUTH__CLIENT_ID` | `FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE` |
| `dwOauth.scope` | `WL_DW_OAUTH__SCOPE` | `openid profile offline_access` |

### Request pacing

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `dwTimeout.minFastRequestMs` | `WL_DW_TIMEOUT__MIN_FAST_REQUEST_MS` | `100` | Minimum spacing for normal fast requests. |
| `dwTimeout.maxFastRequests` | `WL_DW_TIMEOUT__MAX_FAST_REQUESTS` | `350` | Number of fast requests allowed before slower pacing applies. |
| `dwTimeout.minSlowRequestMs` | `WL_DW_TIMEOUT__MIN_SLOW_REQUEST_MS` | `120000` (2 minutes) | Slower pacing interval used after the fast-request threshold. |

Aggressive request pacing can make Daily Wire throttling more likely. Leave these values alone unless you are diagnosing a specific integration problem.

See [[Daily-Wire-Integration]].

---

## Movie metadata (TMDB)

WireLoft can optionally use TMDB to enrich movie metadata, particularly release-date information used for matching and output templates.

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `movieMetadata.tmdbReadAccessToken` | `WL_MOVIE_METADATA__TMDB_READ_ACCESS_TOKEN` | unset | TMDB API Read Access Token. The Settings page does not reveal a stored token back to the browser. |
| `movieMetadata.tmdbApiBaseUrl` | `WL_MOVIE_METADATA__TMDB_API_BASE_URL` | `https://api.themoviedb.org/3` | TMDB API endpoint. |
| `movieMetadata.language` | `WL_MOVIE_METADATA__LANGUAGE` | `en-US` | Preferred metadata language. |
| `movieMetadata.requestTimeoutSeconds` | `WL_MOVIE_METADATA__REQUEST_TIMEOUT_SECONDS` | `10` | Timeout for one TMDB request. |
| `movieMetadata.maxRetries` | `WL_MOVIE_METADATA__MAX_RETRIES` | `2` | Retries for transient TMDB failures, from 0 to 5. |

TMDB is optional and separate from Daily Wire authentication.

---

## Encryption and secret-key settings

These advanced settings control the application key used to protect stored sensitive values.

| Setting | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `crypto.secretKey` | `WL_CRYPTO__SECRET_KEY` | unset | Advanced option for supplying key material directly. Prefer a managed secret/file instead of committing this to YAML. |
| `crypto.secretKeyFile` | `WL_CRYPTO__SECRET_KEY_FILE` | unset | Explicit file containing the application key. |
| `crypto.defaultSecretFile` | `WL_CRYPTO__DEFAULT_SECRET_FILE` | `<project>/data/wl_secret.key`; Docker seed `/config/wl_secret.key` | Generated-key location used when no explicit key is configured. |

Keep the Docker `/config` directory persistent so the generated key survives container recreation. Changing key files can make previously protected authentication data unreadable.

---

## Cron syntax

Cron fields use:

```text
minute hour day-of-month month day-of-week
```

Examples:

```text
*/15 * * * *    # every 15 minutes
0 */6 * * *     # every 6 hours
0 3 * * *       # every day at 03:00
0 8 * * 1,3     # Monday and Wednesday at 08:00
```

Schedules use the `TZ` timezone.

## Example `config.yml`

You only need to include values you actually want to override:

```yaml
logLevel: INFO

downloadSettings:
  downloadRoot: /downloads
  downloadMode: temporary
  temporaryDownloadRoot: /tmp/wireloft-downloads
  rssCacheRoot: /tmp/wireloft-rss-cache
  maxConcurrentDownloads: 3
  filenameRestrictionMode: windows

scheduler:
  maxWorkers: 15
  stalledTaskTimeoutMinutes: 20

newEpisodeSchedule:
  findEpisodesCron: "*/30 * * * *"
  monitorPendingEpisodeCron: "*/2 * * * *"

fileWatcher:
  enabled: true
  scanCron: "*/10 * * * *"
```

Anything omitted continues to use its default unless an environment variable overrides it.