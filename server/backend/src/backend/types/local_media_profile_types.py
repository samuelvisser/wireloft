from enum import StrEnum


class LocalMediaProfileType(StrEnum):
    SHOW = "show"
    MOVIE = "movie"

    # Only used by the polymorphic parent mapper.
    BASE = "base"


class LocalMediaProfileStorageMode(StrEnum):
    SYSTEM = "system"
    DIRECT = "direct"
    TEMPORARY = "temporary"


class LocalMediaProfileThumbnailMode(StrEnum):
    SYSTEM = "system"
    NO_THUMBNAIL = "no_thumbnail"
    EMBED = "embed"
    SIDECAR = "sidecar"
    EMBED_AND_SIDECAR = "embed_and_sidecar"


class ShowLocalMediaProfileScope(StrEnum):
    BOTH = "both"
    PODCAST = "podcast"
    SERIES = "series"


class PreferredFormat(StrEnum):
    FORMAT_4K = 'format_4k'
    FORMAT_1080P = 'format_1080p'
    FORMAT_720P = 'format_720p'
    FORMAT_HLS = 'format_hls'
    FORMAT_AUDIO_ONLY = 'format_audio_only'
