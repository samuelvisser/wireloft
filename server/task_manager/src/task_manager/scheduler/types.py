from enum import Enum


class TaskStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


class OperationStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class OperationSource(str, Enum):
    UI = "UI"
    API = "API"
    SYSTEM = "SYSTEM"


class ResourceType(str, Enum):
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"
    MOVIE = "movie"
    MOVIE_EXTRA = "movie_extra"
    DOWNLOAD_PROFILE = "download_profile"
    DOWNLOAD_PROFILE_SERIES = "download_profile_series"
