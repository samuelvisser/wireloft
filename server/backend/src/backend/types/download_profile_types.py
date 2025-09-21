from enum import Enum


class DownloadProfileType(Enum):
    PODCAST = "podcast"
    SERIES = "series"

    # For instances of DownloadProfileBase class (parent class)
    BASE = "base"

class MediaDownloadStatus(Enum):
    DOWNLOADED = "downloaded"
    DOWNLOADING = "downloading"
    REDOWNLOADED = "redownloaded"
    LOCAL_PROCESSING = "local_processing"
    ERROR = "error"
