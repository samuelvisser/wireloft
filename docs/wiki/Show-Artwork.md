# Show artwork

WireLoft can save shared show artwork alongside your downloaded library. This is separate from the episode thumbnail setting, which embeds images in individual media files or saves episode-level sidecars.

## Enable or override

**Settings / Downloads / Download show assets** controls the system default and is enabled by default. In a Show Local Media Profile, **Download show assets** has three choices: **System**, **Enabled**, or **Disabled**. Existing profiles inherit the system setting.

The corresponding configuration value is:

```yaml
downloadSettings:
  downloadShowAssets: true
```

The help underneath the profile setting shows the resolved show root for the episode currently selected in the Jinja editor. It updates with unsaved template edits and the same editable test values as the episode path. Clearing a test value also clears it for the show-root preview. Both paths use the configured download root and filename restrictions. Previewing does not change saved show metadata, download artwork, or save custom indexes. When no episodes have been indexed, the built-in example can also preview both paths.

## Files and sources

WireLoft writes available images as real JPEG files, using the configured FFmpeg executable:

| File | Source, in preference order |
| --- | --- |
| `poster.jpg` | Show portrait thumbnail, then square thumbnail |
| `fanart.jpg` | Show background image, then landscape thumbnail |
| `square.jpg` | Show square thumbnail |

Missing artwork types are skipped. No arbitrary episode thumbnail is substituted for a show poster.

## How the show folder is chosen

There is no separate root path to configure. WireLoft analyzes the Local Media Profile's Jinja template, including show metadata, variable dependencies, aliases, conditionals and known season names. The root must contain show-specific information and remain inside the download root.

For example:

```jinja
/downloads/TV/{{ show_title }}/Season {{ season_number }}/{{ episode_label }} - {{ title }}.ext
```

resolves to `/downloads/TV/<show title>/`, even when only one season has been indexed. A year or episode-type folder below the show folder likewise does not become the shared show root.

The literal `/downloads/` prefix maps to the configured download root; the preview displays the resulting filesystem path. Different Local Media Profiles can produce separate audio and video roots for the same show. Profiles resolving to the same show directory share its artwork.

Layouts that put different episode types in unrelated trees, omit a show-specific directory, or collide with another show's directory are skipped. The preview explains why a root could not be established. Complex or unsupported Jinja structures are handled conservatively rather than writing a poster into a shared library directory.

## Refresh and file safety

Artwork reconciliation runs after indexing, relevant show/profile/settings changes, successful episode downloads, file renames, and at startup. Initial creation waits for at least one indexed episode. Normal episode scans also refresh available artwork URLs from the already-fetched show page. Existing managed images are checked again on reconciliation after a day, so unchanged URLs do not cause a download on every episode.

WireLoft tracks artwork ownership and content hashes. It leaves pre-existing custom artwork, alternate image formats, and externally modified files untouched. Managed replacements are staged on the destination filesystem and published atomically. The destination filesystem must support hard links for safe, non-overwriting first publication; failures leave existing files untouched and are reported in task logs.

When a template changes, WireLoft creates artwork in the new root. An old managed copy is removed only after a verified replacement exists and tracked media no longer needs the old location. Artwork still shared by another profile is retained. Disabling artwork or deleting a show/profile does not delete existing artwork files.
