# Local Media Profiles

A Local Media Profile defines **what kind of file WireLoft writes and where that file goes**. Download Profiles then reference these profiles to decide which content should be downloaded.

This separation lets one show have several local representations, such as audio-only and 1080p video, without duplicating all the download-selection settings.

## Profile types

### Show

Show profiles can use:

- 4K video
- 1080p video
- 720p video
- audio only

### Movie

Movie profiles can use 4K, 1080p, or 720p video.

## Output templates

Every profile has a Jinja output template. The template:

- must start with `/downloads/`;
- must end with `.ext`;
- may only reference variables valid for that media type.

`.ext` is a WireLoft placeholder: the actual extension is selected from the media format produced by the download.

Example:

```jinja
/downloads/{{ show_title }}/{{ season_name }}/{{ episode_number }} - {{ episode_title }}.ext
```

The `/downloads/` prefix is virtual. It maps to `downloadSettings.downloadRoot`, which is `/downloads` in the supplied Docker configuration.

## Show template variables

| Variable | Meaning |
| --- | --- |
| `show` | Show slug |
| `show_title` | Show title |
| `season` | Season slug, or empty when unavailable |
| `season_name` | Season name, or empty when unavailable |
| `season_index` | WireLoft season index, or empty when unavailable |
| `normalized_season_index` | `0` for an extras season; otherwise the WireLoft season index with any earlier extras seasons removed |
| `extra_seasons_count` | Number of seasons in the show whose lowercased name contains `extra` |
| `is_extra_season` | `1` when the current episode belongs to a season whose lowercased name contains `extra`; otherwise `0` |
| `episode` | Episode slug |
| `episode_title` | Episode title |
| `title` | Alias for the episode title |
| `episode_type` | Parsed episode type |
| `episode_number` | Parsed episode number |
| `episode_label` | Human-facing episode label without the episode-type prefix, for example `2497`, `2497.1`, or `S01E07`; not guaranteed unique |
| `episode_identifier` | Full WireLoft episode identifier including the type prefix, for example `ep.2497`, `ep-extra.2497.1`, or `ep.S01E07`; guaranteed unique within a show |
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

`season_index` is useful for media servers that require numbered season folders even when Daily Wire gives the season a custom name. For example:

```jinja
/downloads/Video/TV Shows/{{ show_title }}/Season {{ season_index }}/{{ show_title }} - {{ date }} - {{ title }}.ext
```

`normalized_season_index` is useful when extras seasons should all map to season `00`, while normal seasons remain consecutively numbered. It is calculated from WireLoft's season indexes: extras seasons return `0`, while a normal season subtracts only extras seasons with a lower WireLoft season index. Extras added later therefore do not change earlier normal-season numbers.

For example, indexes `1: 2022`, `2: Extras 1`, `3: 2023`, `4: Extras 2`, `5: 2024` normalize to `1`, `0`, `2`, `0`, `3`.

The normalized value behaves numerically inside Jinja, so a Plex-style template can use it directly:

```jinja
/downloads/Video/TV Shows/{{ show_title }}/Season {{ "%02d"|format(normalized_season_index) }}/{{ show_title }} - S{{ "%02d"|format(normalized_season_index) }}E{{ "%02d"|format(episode_number|int) }} - {{ title }}.ext
```

`extra_seasons_count` remains available when a template needs the total number of extras seasons, while `is_extra_season` can be used directly as a Jinja condition.

`episode_label` is the human-facing portion with the episode-type prefix removed. It is convenient in filenames but is not guaranteed to be unique. `episode_identifier` preserves the complete WireLoft identifier and is database-guaranteed to be unique within a show. For example, `ep.2497` has the label `2497`, `ep-extra.2497.1` has `2497.1`, and `ep.S01E07` has `S01E07`.

Date-related values can be empty when Daily Wire does not provide the corresponding date. Jinja conditionals are therefore useful when punctuation or folders should only appear when a value exists.

## Movie template variables

Movie templates distinguish the **parent movie** from the **actual downloaded media item**. This matters because a movie can have extras.

### Parent-movie values

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

### Downloaded-item values

These describe the main movie **or** the specific extra currently being downloaded:

| Variable | Meaning |
| --- | --- |
| `slug` | Item slug |
| `title` | Item title |
| `extended_title` | Item extended title |
| `author` | Item author when available |
| `mature_rating` / `rating` | Item rating when available |
| `duration_seconds` | Item duration |
| `media_type` | `movie` for the main feature or the extra type for an extra |
| `date`, `time`, `datetime` | Item date/time values |
| `year`, `month`, `day`, `hour`, `minute`, `second` | Item date/time components |

### Movie collision protection

A Movie Local Media Profile must use at least one item-specific variable. Otherwise, the main movie and an extra could resolve to the same output path and overwrite each other.

Good examples include `{{ title }}`, `{{ slug }}`, `{{ media_type }}`, or an item-specific date field.

Example:

```jinja
/downloads/Movies/{{ movie_title }} ({{ movie_year }})/{{ media_type }} - {{ title }}.ext
```

## Jinja conditionals

Because values such as seasons or dates can be absent, templates can conditionally include text:

```jinja
/downloads/{{ show_title }}/{% if season_name %}{{ season_name }}/{% endif %}{{ episode_title }}.ext
```

The editor previews the rendered path so you can verify the result before saving.

## Filename restrictions

`downloadSettings.filenameRestrictionMode` controls how both literal template components and substituted values are sanitized.

### `unrestricted`

Preserves ordinary Unicode and punctuation as much as possible. WireLoft still removes or replaces path-breaking values such as `/`, `\`, NUL, and control characters so a substituted title cannot create an unexpected directory level.

### `windows` — default

Produces filenames compatible with Windows while retaining Unicode. WireLoft replaces characters Windows does not allow (`< > : " / \ | ? *` and control characters), removes trailing spaces/dots, and protects reserved names such as `CON`, `PRN`, `AUX`, `NUL`, `COM1`, and `LPT1`.

This is the supplied default and is a good cross-platform choice.

### `restricted`

Transliterates decomposable Unicode to ASCII, drops remaining non-ASCII characters, and permits only letters, numbers, `.`, `_`, and `-`. Other runs of characters become underscores.

Use this only when you specifically need conservative ASCII-style filenames.

## Choosing profiles for media servers

A common arrangement is:

- a Show video profile using a Plex/Jellyfin-friendly series hierarchy;
- a separate Show audio profile for Audiobookshelf or podcast-style storage;
- a Movie profile with a conventional movie directory and item-specific extra naming.

The profile only controls WireLoft's output. Your media server can independently scan whichever subdirectories are relevant.
