from enum import Enum


class DownloadProfileType(Enum):
    podcast = "podcast"
    series = "series"

    # For instances of DownloadProfileBase class (parent class)
    base = "base"

class MediaDownloadStatus(Enum):
    downloaded = "downloaded"
    downloading = "downloading"
    redownloaded = "redownloaded"
    local_processing = "local_processing"
    error = "error"
