from enum import Enum


class EpisodePublishStatus(Enum):
    # DW API returns the episode as scheduled
    SCHEDULED = "scheduled"

    # DW API officially returns as delayed
    # This is different from the scheduled time being in the past but the episode not being live yet
    DELAYED = "delayed"

    # DW API returns as live
    LIVE = "live"

    # DW API returns as published, but with the same ID as when it was live. This means the episode is not
    # yet ready to be downloaded.
    DW_PROCESSING = "dw_processing"

    # DW API returns as published with a new ID. This means the episode is ready to be downloaded, but likely
    # still contains the same content as when it was live
    PUBLISHED_WITH_COUNTDOWN = "published_with_countdown"

    # The episode file size changed, meaning it was edited by DW likely meaning it now no longer contains the countdown
    PUBLISHED_FINAL = "published_final"

