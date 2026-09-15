# Download Profiles

Download Profiles decide **which show episodes WireLoft should download automatically**. The attached Local Media Profile decides the file format, download behavior, and output path. See [[Local-Media-Profiles]].

A show can have more than one Download Profile. For example, you can keep audio for every episode while retaining video only for the newest five.

Movies do not use Download Profiles; movie downloads are started manually from the movie page.

## Common options

Every Download Profile lets you choose:

- whether the profile is enabled;
- which episode types it applies to;
- which Local Media Profile should be used for the resulting files.

Disabling a profile keeps its configuration but stops it from automatically selecting new downloads.

## Podcast Download Profiles

Podcast profiles are designed for shows where you usually care about a rolling set of episodes rather than individual seasons.

### Limit by

Choose how many episodes the profile should consider:

- **No limits** — every eligible episode can be downloaded.
- **Date** — only episodes inside a recent number-of-days window are eligible.
- **Number of episodes** — only the newest selected number of eligible episodes are kept in the active window.

### Download starting from

When **No limits** is selected, you can optionally set **Download starting from** to establish a fixed cutoff date.

WireLoft will ignore eligible episodes older than that date and continue downloading new episodes published after it. Existing files are not deleted simply because they predate the cutoff.

This is useful when you want to begin archiving a show from a particular date without downloading its complete history.

### Delete older episodes

When a rolling Date or Number of episodes limit is active, **Delete older episodes** can also remove downloaded files that fall outside that window.

Leave it disabled if you only want the limit to control which new episodes are selected while keeping older files already on disk.

### Countdown and final versions

Some Daily Wire episodes appear with temporary countdown media before the final episode is ready.

- **Download with countdown** allows WireLoft to download that early version.
- **Redownload final version** replaces the early version after the final media becomes available.

If you only want the finished episode, leave countdown downloading disabled.

## Series Download Profiles

Series profiles work by season instead of a rolling podcast window.

### Seasons to download

Select the known seasons that should be covered by the profile. Only selected episode types inside those seasons are eligible.

### Include upcoming seasons

Enable **Include upcoming seasons** when the same rules should automatically apply to seasons The Daily Wire adds later.

This is useful for an ongoing series where you do not want to edit the profile every time a new season appears.

Selecting all seasons in the UI also enables future seasons so the profile keeps following the complete series.

## Using multiple profiles

Multiple Download Profiles are useful whenever format or retention differs. Examples include:

- audio for all regular and auxiliary episodes with no limit;
- 1080p video for regular episodes, latest five only;
- a separate video profile for one particular season;
- a high-quality archive profile alongside a smaller podcast-friendly copy.

Because each profile points to a Local Media Profile, several versions of the same episode can coexist without being treated as the same local file.

## Download Profiles and RSS feeds

An RSS Stream Profile can use files created by any suitable Download Profile. It does not need to be linked to one specific Download Profile.

A common setup is:

1. keep recent episodes downloaded locally;
2. enable **Use Downloads** in the RSS profile;
3. also enable **Use DailyWire stream** as a fallback for older episodes that are no longer stored locally.

See [[Podcast-RSS-Feeds]].

## Global download controls

Settings such as maximum simultaneous downloads, retry attempts, timeout, direct-versus-temporary download behavior, file verification, FFmpeg remuxing, and filename compatibility are configured globally under **Settings → Downloads**.

A Local Media Profile can override the system-wide direct/temporary download behavior when needed. See [[Local-Media-Profiles]] and [[Settings#downloads]].