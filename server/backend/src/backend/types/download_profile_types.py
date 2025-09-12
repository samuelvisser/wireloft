import enum

class DownloadProfileType(enum.Enum):
    show = "show"

class MediaDownloadStatus(enum.Enum):
    downloaded = "downloaded"
    downloading = "downloading"
    redownloaded = "redownloaded"
    local_processing = "local_processing"
    error = "error"
