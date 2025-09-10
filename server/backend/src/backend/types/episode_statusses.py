import enum

class EpisodePublishStatus(enum.Enum):
    scheduled = "scheduled"
    live = "live"
    dw_processing = "dw_processing"
    published = "published"

class EpisodeDownloadStatus(enum.Enum):
    downloaded = "downloaded"
    downloading = "downloading"
    redownloaded = "redownloaded"
    local_processing = "local_processing"
    error = "error"
