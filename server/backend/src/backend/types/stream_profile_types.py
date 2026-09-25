from enum import Enum, StrEnum


class StreamProfileType(Enum):
    RSS = "rss"

    # For instances of StreamProfileBase class (parent class)
    BASE = "base"


class RssVideoOutputMode(StrEnum):
    AUDIO_HLS = "audio_hls"
    AUDIO_MP4 = "audio_mp4"
    MP4 = "mp4"
    MP4_HLS = "mp4_hls"


DEFAULT_RSS_VIDEO_OUTPUT_MODE = RssVideoOutputMode.AUDIO_HLS

RSS_HLS_OUTPUT_MODES = frozenset({
    RssVideoOutputMode.AUDIO_HLS,
    RssVideoOutputMode.MP4_HLS,
})

RSS_MP4_OUTPUT_MODES = frozenset({
    RssVideoOutputMode.AUDIO_MP4,
    RssVideoOutputMode.MP4,
    RssVideoOutputMode.MP4_HLS,
})

RSS_AUDIO_PRIMARY_OUTPUT_MODES = frozenset({
    RssVideoOutputMode.AUDIO_HLS,
    RssVideoOutputMode.AUDIO_MP4,
})
