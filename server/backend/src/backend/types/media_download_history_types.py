from enum import StrEnum


class MediaDownloadHistoryAction(StrEnum):
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
    INTERRUPTED = "interrupted"
    ARTIFACT_REMOVED = "artifact_removed"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_CORRUPTED = "artifact_corrupted"
    ARTIFACT_RESTORED = "artifact_restored"
    ARTIFACT_RENAMED = "artifact_renamed"
