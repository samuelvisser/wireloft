# Automation and Background Tasks

WireLoft uses an internal scheduler and task system to keep managed media current without repeatedly re-indexing everything manually.

Several jobs solve different lifecycle stages: **discovering a new episode**, **watching an episode that exists but is not final yet**, **refreshing metadata after publication**, **cleaning up Daily Wire entries that remain unusable**, **downloading eligible media**, and **verifying files already on disk**.

## Scheduler

The scheduler is enabled by default and uses a thread-pool executor.

Default global behavior:

- scheduler enabled: `true`;
- maximum workers: `5`;
- stalled-task timeout: `20` minutes without a progress-percentage change;
- default retries: `3`;
- retry backoff base: `5` seconds.

The retry delay uses exponential backoff so repeated transient failures do not immediately hammer the same dependency.

WireLoft also watches actively running tasks and operations for stalled progress. Once per minute it samples their progress percentage; when the same percentage remains unchanged for `scheduler.stalledTaskTimeoutMinutes` (20 minutes by default), WireLoft cancels the stalled work and surfaces the reason in the UI. Work that is merely queued or scheduled, and work waiting for a scheduled retry, is excluded because that inactivity is intentional.

APScheduler manages scheduling, concurrency, misfires, and coalescing, but it does not know WireLoft's application-level progress percentage. The stalled-work timeout is therefore implemented by WireLoft's task layer rather than as an APScheduler job option.

Disabling `scheduler.enabled` stops scheduled background jobs. Manual actions can still exist independently, but a disabled scheduler means WireLoft will not perform its normal periodic maintenance.

## New episode discovery

Default schedule:

```text
*/30 * * * *
```

WireLoft searches managed shows for newly published/known episodes every 30 minutes by default.

This is the normal job that answers: **Has Daily Wire added a new episode for this show?**

The discovery worker operates on managed shows rather than requiring a full destructive re-index of your library.

When a newly discovered list entry does not yet have a usable Daily Wire detail endpoint, WireLoft keeps it as `dw_processing` rather than exposing incomplete media. A successful later monitor pass moves it through the normal publication states.

### Sync now

A show's **Sync now** action requests discovery for that particular show immediately. Use it when a new Daily Wire episode is expected but you do not want to wait for the next scheduled pass.

The show sync log records recent attempts and how many new episodes were found, which is useful for distinguishing a scheduler delay from a successful sync that found zero new items.

## Monitoring newly published/live episodes

Default schedule:

```text
*/2 * * * *
```

Some episodes are visible before their final media is ready. WireLoft checks these not-yet-final episodes every two minutes by default.

This is separate from general discovery. Once WireLoft already knows an episode exists, it can monitor that small set without querying the entire library at the same frequency.

A Daily Wire `404` from the episode-detail endpoint is treated as publication state, not as a reason to expose stale media: the local row becomes `dw_processing` and stays under targeted monitoring. The recurring monitor itself is the retry mechanism, so individual monitor runs do not also create scheduler retry chains.

## Worker cron safety

Worker cron settings may not run more frequently than `dwTimeout.minSlowRequestMs`. WireLoft validates this at the Pydantic settings layer for configuration files, environment overrides, and Settings API values.

With the default slow-request delay of 120,000 ms, the shortest valid worker cadence is therefore two minutes. This keeps periodic jobs from continuously filling the Daily Wire fast-request budget faster than its cooldown can clear it.

The rule applies to all configurable worker cron schedules: episode discovery, pending-episode monitoring, stuck-processing cleanup, download verification, and file-watcher scans.

## Countdown versus final publication

Two timing thresholds help WireLoft interpret Daily Wire's publication state:

- **Published countdown after:** 20 minutes.
- **Published final after:** 180 minutes.

The final threshold cannot be shorter than the countdown threshold.

`episodeStatusTiming.publishedFinalAfterMinutes` is an absolute safety fallback measured directly from the episode's `publishedAt`: after that many minutes, an otherwise ambiguous successful Daily Wire response is treated as final. A currently missing (`404`) detail endpoint and a `No Show Today` placeholder deliberately override that fallback and remain `dw_processing`, because neither is usable media.

Podcast Download Profiles can use these stages to decide whether to download an early countdown version and whether to redownload the later final version.

## Metadata refresh after publication

Even after an episode is considered published, metadata such as a title, thumbnail or episode number can change. WireLoft therefore schedules targeted metadata refreshes after publication.

Default offsets:

```text
5m,15m,30m,1h,3h,6h,24h
```

This sequence is intentionally an offset list rather than a cron schedule: it says how long after an episode's publication WireLoft should revisit that episode's metadata.

Values support seconds (`s`), minutes (`m`), hours (`h`), and days (`d`). They must be positive, unique, and strictly increasing.

A metadata refresh also reconciles WireLoft's episode identifier when Daily Wire corrects an episode number after publication. This is particularly useful when an item was temporarily published as an episode extra and later corrected to the main episode number.

This targeted strategy allows recent/live episodes to settle without repeatedly rechecking the entire historical library.

## Stuck `dw_processing` cleanup

Default schedule:

```text
0 * * * *
```

WireLoft runs `check_episodes_stuck_at_dw_processing` once per hour by default. The worker handles two disposable Daily Wire failure modes through the same generic publication state:

- `No Show Today` placeholders are placed in `dw_processing` as soon as they are detected;
- ordinary episode entries whose detail endpoint returns `404` are also placed in `dw_processing` while WireLoft waits for Daily Wire to make them usable again.

An entry is deleted only when both the episode itself and the same continuous placeholder/404 processing incident are at least four hours old. For a 404 episode WireLoft verifies the detail endpoint once more before deleting it; a successful response clears the stale-404 incident instead.

The existing setting name `newEpisodeSchedule.checkNoShowTodayCron` and its environment-variable equivalent are retained for backward compatibility, but they now control this broader cleanup worker.

Because download and stream eligibility already rejects `dw_processing`, profiles do not need a separate `No Show Today` exception.

## Download execution

Download Profiles decide eligibility; the global download settings control execution.

Defaults:

- maximum concurrent downloads: `5`;
- maximum attempts: `3`;
- timeout per attempt: `600` seconds;
- downloaded-video remux to MP4: enabled.

Each required download is represented as a normal `media.download` TaskOperation. The shared download lane reserves TaskRuns before dispatch so queued work cannot bypass `maxConcurrentDownloads`; after a restart, unfinished operations are recovered through the same queue instead of inferring interrupted work from fields on the MediaDownload record.

See [[Download-Profiles]] and [[Settings#downloads]].

## Download verification

Default verification schedule:

```text
0 */2 * * *
```

Every two hours by default, WireLoft runs its download verification workflow. This is separate from the file watcher's more frequent disk-state reconciliation.

## File watcher

Default scan schedule:

```text
*/10 * * * *
```

The file watcher keeps the database's downloaded-file state aligned with disk. With file-size verification enabled, a file is considered suspicious/corrupted when it is empty or smaller than the size WireLoft recorded when the download completed.

The watcher follows the path recorded for the download. It should not be treated as a general filesystem organizer: manually renaming or moving a managed file can make the original recorded path appear missing.

## Cron syntax

WireLoft's scheduled cron settings use five fields:

```text
minute hour day-of-month month day-of-week
```

Examples:

```text
*/15 * * * *    # every 15 minutes
0 */6 * * *     # every 6 hours at minute 0
0 3 * * *       # daily at 03:00
0 8 * * 1,3     # Monday and Wednesday at 08:00
```

Schedules use the WireLoft application timezone, configured with `TZ`.

## Tuning advice

More frequent is not always better. Discovery and metadata jobs call external Daily Wire services; extremely aggressive schedules can increase remote request volume without materially improving the user experience.

Prefer targeted workers as designed:

- keep general discovery moderate;
- use the pending-episode monitor for already-known publishing episodes;
- use post-publication metadata intervals for titles/thumbnails/numbers that may settle later;
- let the hourly processing cleanup deal with entries Daily Wire never makes usable;
- use **Sync now** for the occasional show that you need immediately.

See [[Settings]] for every exact configuration key and environment-variable equivalent.
