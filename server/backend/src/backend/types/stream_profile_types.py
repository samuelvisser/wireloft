from enum import Enum


class StreamProfileType(Enum):
    RSS = "rss"

    # For instances of StreamProfileBase class (parent class)
    BASE = "base"


class RssDwVideoMethod(str, Enum):
    STREAM_HLS_DOWNLOAD_M4A = "stream_hls_download_m4a"
    STREAM_DOWNLOAD_MP4 = "stream_download_mp4"
    STREAM_HLS_DOWNLOAD_MP4 = "stream_hls_download_mp4"


DEFAULT_RSS_DW_VIDEO_METHOD = RssDwVideoMethod.STREAM_HLS_DOWNLOAD_M4A.value
