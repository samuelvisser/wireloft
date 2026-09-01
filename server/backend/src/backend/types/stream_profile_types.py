from enum import Enum


class StreamProfileType(Enum):
    RSS = "rss"

    # For instances of StreamProfileBase class (parent class)
    BASE = "base"


class RssDwVideoMethod(str, Enum):
    PODCASTING_2_0 = "podcasting_2_0"
    CACHED_MP4 = "cached_mp4"


DEFAULT_RSS_DW_VIDEO_METHOD = RssDwVideoMethod.PODCASTING_2_0.value
