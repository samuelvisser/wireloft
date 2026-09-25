from enum import Enum


class MediaDownloadHistoryAction(str, Enum):
    """Durable user-meaningful events in one MediaDownload's lifetime."""

    CREATED = "created"
    QUEUED = "queued"
    PRIORITIZED = "prioritized"
    RETRY_REQUESTED = "retry_requested"
    RESTARTED = "restarted"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    ARTIFACT_REMOVED = "artifact_removed"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_CORRUPTED = "artifact_corrupted"
    ARTIFACT_RESTORED = "artifact_restored"
    ARTIFACT_RENAMED = "artifact_renamed"
