from enum import Enum


class StreamProfileType(Enum):
    RSS = "rss"

    # For instances of StreamProfileBase class (parent class)
    BASE = "base"


class RssDwVideoMethod(str, Enum):
    STREAM_HLS_DOWNLOAD_M4A = "stream_hls_download_m4a"
    STREAM_DOWNLOAD_MP4 = "stream_download_mp4"
    STREAM_HLS_DOWNLOAD_MP4 = "stream_hls_download_mp4"

    # WireLoft 1.1 compatibility experiments. These deliberately keep the
    # podcast-facing URL stable and isolate individual HTTP/HLS behaviours so
    # Pocket Casts ingestion and AVPlayer playback can be tested separately.
    EXPERIMENT_HLS_REDIRECT_302 = "experiment_hls_redirect_302"
    EXPERIMENT_HLS_HTTPS_REDIRECT_302 = "experiment_hls_https_redirect_302"
    EXPERIMENT_HLS_REDIRECT_307 = "experiment_hls_redirect_307"
    EXPERIMENT_HLS_REDIRECT_308 = "experiment_hls_redirect_308"
    EXPERIMENT_HLS_CACHED_REDIRECT_302 = "experiment_hls_cached_redirect_302"
    EXPERIMENT_HLS_HEAD_200_GET_302 = "experiment_hls_head_200_get_302"
    EXPERIMENT_HLS_REDIRECT_302_HEADERS = "experiment_hls_redirect_302_headers"
    EXPERIMENT_HLS_PREWARMED_RAW = "experiment_hls_prewarmed_raw"
    EXPERIMENT_HLS_PREWARMED_ABSOLUTE = "experiment_hls_prewarmed_absolute"
    EXPERIMENT_HLS_PROXY_VIDEO_X = "experiment_hls_proxy_video_x"
    EXPERIMENT_HLS_PROXY_MASTER_X = "experiment_hls_proxy_master_x"
    EXPERIMENT_HLS_PROXY_INDEX_X = "experiment_hls_proxy_index_x"
    EXPERIMENT_HLS_PROXY_VIDEO_APPLE = "experiment_hls_proxy_video_apple"
    EXPERIMENT_HLS_PROXY_VIDEO_GENERIC = "experiment_hls_proxy_video_generic"
    EXPERIMENT_HLS_PREPARED_TS = "experiment_hls_prepared_ts"


DEFAULT_RSS_DW_VIDEO_METHOD = RssDwVideoMethod.STREAM_HLS_DOWNLOAD_M4A.value
