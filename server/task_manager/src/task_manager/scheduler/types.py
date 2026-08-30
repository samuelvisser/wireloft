from enum import Enum


class TaskStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


class ResourceType(str, Enum):
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"
    MOVIE = "movie"
    TRAILER = "trailer"
    DOWNLOAD_PROFILE = "download_profile"
    DOWNLOAD_PROFILE_SERIES = "download_profile_series"
