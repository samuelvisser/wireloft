from enum import Enum


class LocalMediaProfileType(str, Enum):
    SHOW = "show"
    MOVIE = "movie"

    # Only used by the polymorphic parent mapper.
    BASE = "base"


class ShowLocalMediaProfileScope(str, Enum):
    BOTH = "both"
    PODCAST = "podcast"
    SERIES = "series"


class PreferredFormat(str, Enum):
    FORMAT_4K = 'format_4k'
    FORMAT_1080P = 'format_1080p'
    FORMAT_720P = 'format_720p'
    FORMAT_AUDIO_ONLY = 'format_audio_only'
