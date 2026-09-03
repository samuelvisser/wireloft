# Shows and Library

WireLoft's Library is the local index of Daily Wire content you have chosen to manage. Adding an item to the Library is separate from downloading it: a show can be fully indexed while all media remains on Daily Wire.

## Browse versus Library

**Browse** is used to discover Daily Wire shows and movies that WireLoft can add. **Library** contains the shows and movies already managed by your WireLoft instance.

This distinction lets you use WireLoft as an index first and decide later whether each item should be downloaded, exposed through RSS, or both.

## Shows

A show contains its seasons and episodes plus the profiles that determine local downloads and RSS behavior.

When adding a show, WireLoft's wizard can configure three independent concerns:

- **Local Media Profile** — format and output path for files written to disk.
- **Download Profile** — which content should be downloaded automatically.
- **Stream Profile** — how the show's private RSS feed should expose media.

You can add a show without enabling either downloads or RSS.

### Show types

Download behavior differs between Podcast and Series profiles:

- **Podcast** profiles use rolling limits such as a number of days or latest episode count, plus countdown/final-version behavior.
- **Series** profiles select explicit seasons and can automatically include future seasons.

See [[Download-Profiles]].

## Episodes and episode types

WireLoft identifies Daily Wire items by episode type. Profiles can choose which types they apply to. The common defaults for a podcast/RSS workflow are regular **Episode** (`ep`) and **Auxiliary** (`aux`) items.

An episode's page shows the media known to WireLoft and any local downloads. Media that is still live or otherwise not ready for normal download can remain indexed without an immediately downloadable file.

## Publication and live episodes

Daily Wire episodes can change after first appearing. A live/published item may initially contain a countdown version, and metadata can also be updated after publication.

WireLoft therefore separates discovery from publication monitoring:

- a normal discovery job looks for new episodes;
- a faster monitor checks episodes that exist but are not yet considered fully published;
- finalized episode metadata is refreshed at a configurable sequence of offsets after publication.

The defaults are documented in [[Automation-and-Background-Tasks]] and [[Settings]].

## Sync now and sync history

A show can be synchronized manually when you do not want to wait for the next scheduled discovery pass. WireLoft also records recent show-sync activity so you can distinguish "the worker has not run yet" from "the worker ran and found nothing new."

A manual synchronization runs discovery for that show rather than forcing a full-library re-index.

## Seasons

Series Download Profiles can select any combination of known seasons. **Include upcoming seasons** tells WireLoft to continue applying that profile when new seasons appear, avoiding the need to edit the profile every time a season is added.

## Movies and extras

Movies are managed separately from shows. Movie Local Media Profiles require a video format and their output template must distinguish the main movie from its extras. This prevents two different media items from resolving to the same file path.

Movie metadata may optionally be enriched with TMDB data, primarily for release-date lookups used by output templates. Configure TMDB under [[Settings]].

## Removing content

Deleting a profile and deleting media are different operations. A Local Media Profile describes storage; a Download Profile describes automation; the downloaded media itself has its own lifecycle and status.

Before deleting a profile that is in use, review the profiles attached to the show and any download retention rules. This is especially important when automatic deletion of old podcast episodes is enabled.