from enum import Enum, StrEnum


class DownloadProfileType(Enum):
    PODCAST = "podcast"
    SERIES = "series"

    # For instances of DownloadProfileBase class (parent class)
    BASE = "base"


class MediaDownloadArtifactStatus(str, Enum):
    """Persistent state of the file represented by a MediaDownload.

    Execution state deliberately does not live here. Queued/running/failed/canceled
    attempts are TaskRun/TaskOperation state; this enum only describes the artifact
    that currently exists (or does not exist) on disk.
    """

    ABSENT = "absent"
    AVAILABLE = "available"
    MISSING = "missing"
    CORRUPTED = "corrupted"


class MediaDownloadStatus(Enum):
    """Legacy wire values kept for migration/test compatibility only.

    Runtime code must use TaskRun/TaskOperation for execution state and
    MediaDownloadArtifactStatus for persistent file state.
    """

    PENDING = "pending"
    DOWNLOADED = "downloaded"
    DOWNLOADING = "downloading"
    REDOWNLOADED = "redownloaded"
    LOCAL_PROCESSING = "local_processing"
    CANCELLED = "cancelled"
    ERROR = "error"
    MISSING = "missing"
    CORRUPTED = "corrupted"


# Types for the episode identification field
class EpIdType(StrEnum):
    EP = "ep"
    EP_EXTRA = "ep-extra"
    TRAILER = "trailer"
    AUX = "aux"
