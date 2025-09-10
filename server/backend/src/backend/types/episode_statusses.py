import enum

class EpisodePublishStatus(enum.Enum):
    # DW API returns the episode as scheduled
    scheduled = "scheduled"

    # DW API officially returns as delayed
    # This is different from the scheduled time being in the past but the episode not being live yet
    delayed = "delayed"

    # DW API returns as live
    live = "live"

    # DW API returns as published, but with the same ID as when it was live. This means the episode is not
    # yet ready to be downloaded.
    dw_processing = "dw_processing"

    # DW API returns as published with a new ID. This means the episode is ready to be downloaded, but likely
    # still contains the same content as when it was live
    published_with_countdown = "published_with_countdown"

    # The episode file size changed, meaning it was edited by DW likely meaning it now no longer contains the countdown
    published_final = "published_final"

class EpisodeDownloadStatus(enum.Enum):
    downloaded = "downloaded"
    downloading = "downloading"
    redownloaded = "redownloaded"
    local_processing = "local_processing"
    error = "error"
