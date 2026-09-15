# Automation and Background Tasks

WireLoft performs routine work automatically so you do not have to keep refreshing shows or manually checking every download.

For most installations, the defaults are a good balance between keeping content current and avoiding unnecessary Daily Wire requests.

## Default automation

| What WireLoft checks | Default |
| --- | --- |
| New episodes on managed shows | Every 30 minutes |
| Known episodes that are still publishing | Every 2 minutes |
| Episodes temporarily without usable media | Every 20 minutes |
| Recent episode metadata | 15m, 30m, 1h, 3h, 6h, 24h, 3d after publication |
| Download verification | Every 2 hours |
| Tracked files on disk | Every 10 minutes |
| Stalled task timeout | 20 minutes without progress |

All of these can be adjusted from **Settings**, but there is usually no need to make them more aggressive.

## Finding new episodes

Every 30 minutes by default, WireLoft checks the shows in your Library for newly known episodes.

This is the normal automatic discovery process. It does not mean every episode is downloaded; Download Profiles decide what happens after an episode has been found.

### Sync now

Use a show's **Sync now** action when you know something new has appeared on The Daily Wire and you do not want to wait for the next scheduled check.

The show keeps recent synchronization results so you can see whether WireLoft checked successfully and whether anything new was found.

## Following live and newly published episodes

An episode can become visible before its final media is ready. WireLoft therefore keeps checking recent episodes that are still scheduled, live, processing, or using temporary countdown media.

By default, these episodes are rechecked every two minutes. Once the episode settles into its final state, the frequent monitoring stops automatically.

Podcast Download Profiles can decide whether they should wait for the final media or download an early countdown version. See [[Download-Profiles]].

## Recent metadata updates

The Daily Wire sometimes changes titles, thumbnails, episode numbers, or other information shortly after publication.

WireLoft revisits newly published episodes at several gradually increasing intervals:

```text
15m,30m,1h,3h,6h,24h,3d
```

This keeps recent metadata accurate without repeatedly refreshing the entire historical library.

## Episodes without usable media

Sometimes The Daily Wire lists an episode but does not (yet) provide usable media for it. This can be temporary, so WireLoft does not immediately remove the episode.

By default, WireLoft rechecks these episodes every 20 minutes. If usable media returns, the episode becomes available to downloads and RSS profiles again automatically.

If an episode remains unavailable and The Daily Wire continues to confirm that it is no longer available, WireLoft can eventually remove the stale entry. The default waiting period is **4 hours**.
WireLoft only removes episodes after those 4 hours if The Daily Wire does not have them listed on their site either (in other words, if it 404's).

On an affected episode page, **Early Delete** lets you request that cleanup immediately instead of waiting for the normal delay. WireLoft still checks the current Daily Wire state before removing it.

## Download queue

Download Profiles and manual actions add work to the central download queue. By default, WireLoft allows up to **5 downloads at once**.

If all download slots are busy, additional downloads remain queued. You can use **Prioritize** on a queued item to make it one of the next downloads selected when a slot opens. Download actions started manually are automatically prioritized.

See [[Downloads-and-File-Integrity]].

## Retries and stalled work

Background work can fail temporarily because of network problems, upstream errors, storage issues, or other transient conditions. WireLoft automatically retries eligible tasks according to the configured retry settings.

The default background-task retry count is **3**, with increasing pauses between attempts.

WireLoft also watches work that is supposed to be making progress. If its progress does not change for **20 minutes** by default, the work is treated as stalled and cancelled rather than being allowed to sit indefinitely.

## Download verification and file watching

Two background checks help keep the download list aligned with your actual files:

- **Download verification** runs every two hours by default.
- The **file watcher** checks tracked files every ten minutes by default.

These checks can detect missing files and, when enabled, obviously truncated files. WireLoft can also recover some same-folder renames.

See [[Downloads-and-File-Integrity]] for more details.

## Scheduler settings

The background scheduler is enabled by default. Disabling it stops normal automatic indexing, monitoring, verification, and scheduled download behavior after restart.

The default **Maximum workers** value is **15**. This controls how much general background work can run in parallel; download concurrency is controlled separately by **Concurrent downloads**.

Unless you are diagnosing a specific performance problem, leave the scheduler settings at their defaults.

## Cron schedules

Settings that use cron follow the UNIX five-field format:

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

Schedules use WireLoft's configured timezone (`TZ`).

WireLoft validates worker schedules against its Daily Wire request-pacing settings, so schedules that are unreasonably frequent may be rejected rather than creating constant upstream traffic.

## Tuning advice

More frequent checks are rarely necessary. If you occasionally need a show updated immediately, use **Sync now** instead of making every show refresh much more often.

If you do tune automation:

- keep general episode discovery moderate;
- leave frequent monitoring to episodes that are actually still publishing;
- keep the gradual metadata-refresh sequence for recently published episodes;
- avoid increasing both scheduler concurrency and download concurrency without considering CPU, storage, and network capacity.

See [[Settings#automation]] for the exact configurable values.