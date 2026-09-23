from enum import Enum


class StreamProfileType(Enum):
    RSS = "rss"

    # For instances of StreamProfileBase class (parent class)
    BASE = "base"


class RssVideoOutputMode(str, Enum):
    AUDIO_HLS = "audio_hls"
    AUDIO_MP4 = "audio_mp4"
    MP4 = "mp4"
    MP4_HLS = "mp4_hls"


DEFAULT_RSS_VIDEO_OUTPUT_MODE = RssVideoOutputMode.AUDIO_HLS.value

RSS_HLS_OUTPUT_MODES = frozenset({
    RssVideoOutputMode.AUDIO_HLS.value,
    RssVideoOutputMode.MP4_HLS.value,
})

RSS_MP4_OUTPUT_MODES = frozenset({
    RssVideoOutputMode.AUDIO_MP4.value,
    RssVideoOutputMode.MP4.value,
    RssVideoOutputMode.MP4_HLS.value,
})

RSS_AUDIO_PRIMARY_OUTPUT_MODES = frozenset({
    RssVideoOutputMode.AUDIO_HLS.value,
    RssVideoOutputMode.AUDIO_MP4.value,
})
