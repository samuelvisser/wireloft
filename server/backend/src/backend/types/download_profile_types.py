import enum

class DownloadProfileType(enum.Enum):
    podcast = "podcast"
    series = "series"

    # For instances of DownloadProfileBase class (parent class)
    base = "base"

class MediaDownloadStatus(enum.Enum):
    downloaded = "downloaded"
    downloading = "downloading"
    redownloaded = "redownloaded"
    local_processing = "local_processing"
    error = "error"
