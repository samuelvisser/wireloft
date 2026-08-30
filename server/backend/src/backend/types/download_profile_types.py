from enum import Enum, StrEnum


class DownloadProfileType(Enum):
    PODCAST = "podcast"
    SERIES = "series"

    # For instances of DownloadProfileBase class (parent class)
    BASE = "base"

class MediaDownloadStatus(Enum):
    # Download requested but not picked up by the download worker yet
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    DOWNLOADING = "downloading"
    REDOWNLOADED = "redownloaded"
    LOCAL_PROCESSING = "local_processing"
    CANCELLED = "cancelled"
    ERROR = "error"
    # The file watcher could not find the file that was previously downloaded
    MISSING = "missing"
    # The file watcher found the file, but it is empty or smaller than expected
    CORRUPTED = "corrupted"

# Types for the episode identification field
class EpIdType(StrEnum):
    EP = "ep"
    EP_EXTRA = "ep-extra"
    TRAILER = "trailer"
    AUX = "aux"
