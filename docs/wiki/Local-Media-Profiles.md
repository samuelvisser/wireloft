# Local Media Profiles

A Local Media Profile describes **the local file WireLoft should create**. It controls the preferred format, where the file is stored, and whether incomplete download work is written directly in the library or staged elsewhere first.

Download Profiles use Local Media Profiles for automatic show downloads. Movies also use Local Media Profiles, but movie downloads are started manually.

## Show and Movie profiles

### Show profiles

Show profiles can use:

- 4K video;
- 1080p video;
- 720p video;
- audio only.

A Show profile also has an **Available for** setting. This controls where WireLoft offers the profile in the interface.

### Movie profiles

Movie profiles can use 4K, 1080p, or 720p video. The same profile can be used for the main movie and its extras, so its output template must keep those items distinct.

## Download behavior

Each Local Media Profile can choose how downloads using it are written:

- **System** — follow the current system-wide default from **Settings → Downloads**.
- **Save directly to downloads** — perform the download in the destination area. This is the simplest and usually fastest option.
- **Save to temporary folder first** — keep incomplete download and processing work in the configured temporary folder, then place the completed file in the media library.

Temporary mode is useful when Plex, Jellyfin, or another application actively watches the destination folder and you do not want it to see partly downloaded media.

The temporary folder may be on different storage from the final library. Configure the system default and temporary location under [[Settings#downloads]].

## Preferred format

The preferred format is the quality or media type WireLoft should request when this profile is used.

A profile represents one local variant. If you want both audio and 1080p copies of the same episode, create separate Local Media Profiles and use them from separate Download Profiles.

## Output templates

The output template controls the folder structure and filename. WireLoft uses Jinja variables so one template can produce a unique path for every episode, movie, or extra.

A simple show example is:

```jinja
/downloads/{{ show_title }}/{{ episode_title }}.ext
```

A media-server-friendly series example is:

```jinja
/downloads/TV Shows/{{ show_title }}/Season {{ season_index }}/{{ show_title }} - {{ episode_label }} - {{ title }}.ext
```

`.ext` is a WireLoft placeholder. It is replaced with the extension that matches the file WireLoft actually produces.

### Path requirements

After Jinja is evaluated, the output path must:

- begin with `/downloads/`;
- end with `.ext`.

Most templates should simply begin with `/downloads/`. Advanced templates may place Jinja setup statements before it as long as those statements do not output any text.

For example:

```jinja
{% set folder = show_title %}/downloads/{{ folder }}/{{ episode_title }}.ext
```

The `/downloads/` prefix maps to WireLoft's configured **Download root**. In a normal Docker installation that is the mounted media directory.

### Use the editor preview

The Local Media Profile editor includes a variable picker and path preview. Use those rather than memorizing the full reference below. The preview is especially helpful when optional values or Jinja conditionals are involved.

### Custom metadata

Shows and movies can store user-defined **Custom metadata**. This is useful when a media server needs a value that The Daily Wire and WireLoft do not know automatically.

For example, if Plex should see a show folder named `Parenting (2026)` but no release year is available from The Daily Wire, add this metadata to the show:

- field: `year`
- value: `2026`

Show metadata is then available in Show Local Media Profile templates as:

```jinja
{{ meta_show_year }}
```

A complete example is:

```jinja
/downloads/TV Shows/{{ show_title }} ({{ meta_show_year }})/{{ title }}.ext
```

Metadata fields are shared within their media type. Adding a `year` field to one show makes that same field available on every show, but each show stores its own value. A show that has no value for `year` simply exposes `{{ meta_show_year }}` as an empty value. Movie metadata works the same way, independently from show metadata.

Custom metadata variables use these prefixes:

| Metadata owner | Template variable prefix | Available in |
| --- | --- | --- |
| Show | `meta_show_` | Show Local Media Profiles |
| Movie | `meta_movie_` | Movie Local Media Profiles |

Field names use lowercase letters, numbers, and underscores and must begin with a letter or underscore. Once a custom metadata field exists, the corresponding variable appears in the output-template autocomplete and in the editor's available-variable reference.

Changing a custom metadata value affects future path resolution. WireLoft does not move already-downloaded files merely because a metadata value changed; use the existing rename-file action where applicable if you want existing show files to adopt the new path.

## Optional values and conditionals

Some metadata, such as a release date, may not exist for every item. Missing values are empty, so Jinja conditionals can omit the punctuation or folder that belongs with them.

Example:

```jinja
/downloads/{{ show_title }}/{{ episode_title }}{% if year %} ({{ year }}){% endif %}.ext
```

## Show template variable reference

| Variable | Meaning |
| --- | --- |
| `show` | Show slug |
| `show_title` | Show title |
| `season` | Season slug, or empty when unavailable |
| `season_name` | Season name, or empty when unavailable |
| `season_index` | WireLoft season index, or empty when unavailable |
| `episode` | Episode slug |
| `episode_title` | Episode title |
| `title` | Episode title |
| `episode_type` | Parsed episode type |
| `episode_number` | Parsed episode number |
| `episode_label` | Human-facing episode label without the type prefix; convenient but not guaranteed unique |
| `episode_identifier` | Full WireLoft episode identifier; unique within the show |
| `episode_published_date` | Publication date as `YYYY-MM-DD` |
| `episode_published_time` | Publication time as `HH:MM:SS` |
| `episode_published_datetime` | Publication date and time |
| `date` | Generic episode date value |
| `time` | Generic episode time value |
| `datetime` | Generic episode date/time value |
| `year` | Four-digit year |
| `month` | Month value |
| `day` | Day value |
| `hour` | Hour value |
| `minute` | Minute value |
| `second` | Second value |

`season_index` is useful when a media server expects numbered season folders even if The Daily Wire uses custom season names.

## Movies and extras

Movie templates have two groups of values:

- variables beginning with `movie_` always describe the parent movie;
- variables without that prefix describe the actual item being downloaded, which can be either the main movie or a specific movie extra.

This makes it possible to keep all extras inside the movie's folder while giving each item its own filename.

Example:

```jinja
/downloads/Movies/{{ movie_title }}{% if movie_year %} ({{ movie_year }}){% endif %}/{{ media_type }} - {{ title }}.ext
```

A movie template must use an item-specific value such as `{{ title }}`, `{{ slug }}`, or `{{ media_type }}` so the main movie and an extra cannot resolve to the same output path.  
WireLoft never overwrites existing files if the same output path is generated for multiple items, but it is
still a case that should be avoided to make it obvious what content is in a file.

### Parent movie variables

| Variable | Meaning |
| --- | --- |
| `movie_slug` | Parent movie slug |
| `movie_title` | Parent movie title |
| `movie_extended_title` | Parent movie extended title |
| `movie_author` | Parent author/creator value |
| `movie_mature_rating` | Parent mature rating |
| `movie_duration_seconds` | Parent duration in seconds |
| `movie_date`, `movie_time`, `movie_datetime` | Parent release-date values |
| `movie_year`, `movie_month`, `movie_day` | Parent release-date components |
| `movie_hour`, `movie_minute`, `movie_second` | Parent release-time components |

### Current item variables

These describe the main movie or the specific extra currently being downloaded:

| Variable | Meaning |
| --- | --- |
| `slug` | Item slug |
| `title` | Item title |
| `extended_title` | Item extended title |
| `author` | Item author when available |
| `mature_rating` / `rating` | Item rating when available |
| `duration_seconds` | Item duration |
| `media_type` | `movie` for the main feature, or the extra type |
| `date`, `time`, `datetime` | Item date/time values |
| `year`, `month`, `day`, `hour`, `minute`, `second` | Item date/time components |

The Daily Wire does not always provide every field for movie extras. Use conditionals around values that may be empty.

## Filename restrictions

The global **Filename restrictions** setting controls how template text and substituted values are made safe for filesystems.

### Minimal restrictions (`unrestricted`)

Preserves most Unicode and punctuation while still preventing characters that would accidentally create a new path or invalid filename.

### Windows-compatible filenames (`windows`) — default

Keeps Unicode while replacing characters Windows does not allow and protecting reserved Windows names. This is a good cross-platform default.

### Restricted filenames (`restricted`)

Produces conservative ASCII-style filenames using letters, numbers, `.`, `_`, and `-`.

Use this only when another application or filesystem needs very simple filenames.

## Suggested layouts

A common arrangement is:

- one Show video profile for Plex/Jellyfin;
- one Show audio profile for podcast-style storage or Audiobookshelf;
- one Movie profile with a conventional movie folder and item-specific extra names.

Local Media Profiles only control files WireLoft creates. Your media server can independently scan whichever subfolders you want.
