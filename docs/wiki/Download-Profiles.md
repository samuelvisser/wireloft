# Download Profiles

Download Profiles decide **which media WireLoft should download automatically**. They do not decide where the file is stored or which format is written; that comes from the attached [[Local-Media-Profiles]].

A show can have multiple Download Profiles. For example, you can keep audio for every regular and auxiliary episode while retaining video only for full episodes.

## Common fields

Every Download Profile has:

- **Enable profile** — keep the configuration while temporarily disabling its automatic behavior.
- **Episode types** — which Daily Wire episode types are eligible.
- **Local Media Profile** — the format and output-template destination used for those downloads.

Because a Local Media Profile includes the preferred format, multiple Download Profiles can target different versions of the same episode.

## Podcast Download Profiles

Podcast profiles are designed for rolling episode libraries.

### Download with countdown

Some Daily Wire episodes appear before the final media is ready and initially contain the countdown used around live shows.

Enable **Download with countdown** if you want WireLoft to download that early version. If it is disabled, WireLoft waits until the episode is considered past the countdown stage.

### Redownload final version

When countdown downloading is enabled, **Redownload final version** lets WireLoft replace that early file with the finalized media after the countdown is expected to have disappeared.

The timing used to decide those publication stages is configurable under `episodeStatusTiming`; see [[Settings]].

### Limit downloads

A Podcast Download Profile can be unlimited or use exactly one rolling limit:

- **Date** — download eligible episodes from the most recent number of days.
- **Number of episodes** — download only the newest X eligible episodes.

The backend rejects a profile that has both limits active at once.

When limiting is first enabled in the UI, the date mode starts at **180 days**. Switching to episode-count mode starts at **5 episodes**. These are form conveniences; at the API/database level a value of `0` means that limit is disabled.

### Delete older episodes

When a rolling limit is enabled, **Delete older episodes** can remove previously downloaded files that fall outside that limit.

- With a date limit, files older than the rolling date window become eligible for removal.
- With an episode-count limit, files outside the newest selected number of eligible episodes become eligible for removal.

Leave this disabled if you want the limit to affect future download selection without pruning older files already on disk.

## Series Download Profiles

Series profiles work by season rather than by a rolling podcast window.

### Seasons to download

Select one or more known seasons. Only eligible episode types within the selected seasons are handled by the profile.

### Include upcoming seasons

Enable **Include upcoming seasons** if the same profile should automatically apply to seasons that do not exist yet. This is useful for ongoing series.

**Select all** in the UI selects all currently known seasons and enables upcoming seasons as well.

## Multiple profiles for one show

Multiple profiles are useful when retention or formats differ. Examples:

- audio-only for `Episode` + `Auxiliary`, unlimited;
- 1080p video for `Episode`, latest 5 only;
- a second video profile for a specific season;
- high-resolution archive profile alongside a smaller RSS-friendly profile.

WireLoft tracks each downloaded media variant through its Local Media Profile, so several representations of the same episode can coexist.

## Download profiles and RSS

An RSS Stream Profile can use files created by Download Profiles, but it does not directly depend on one specific Download Profile. It searches completed downloads for a media file that matches the RSS profile's desired format and episode type.

If **Use Downloads** and **Use DailyWire stream** are both enabled, an acceptable completed local download is preferred and Daily Wire is the fallback. See [[Podcast-RSS-Feeds]].

## Global download controls

Concurrency, retry attempts, per-download timeout, verification frequency, MP4 remuxing, FFmpeg path, filename compatibility, and the physical download root are global settings rather than per-profile options. See [[Settings#downloads]].