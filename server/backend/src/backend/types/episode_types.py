from enum import Enum


class EpisodePublishStatus(Enum):
    # Daily Wire explicitly reports the episode as scheduled.
    SCHEDULED = "scheduled"

    # Daily Wire exposes the delayed-start slug marker. WireLoft treats this as
    # authoritative rather than inferring delay from an elapsed scheduled time.
    DELAYED = "delayed"

    # Daily Wire explicitly reports the episode as live.
    LIVE = "live"

    # WireLoft quarantines the episode because Daily Wire currently exposes no
    # settled usable media. The dedicated no-usable-media worker owns this state.
    NO_USABLE_MEDIA = "no_usable_media"

    # Daily Wire reports PUBLISHED while metadata duration is still below 12
    # seconds but the actual HLS playlist is already longer than 12 seconds.
    DW_PROCESSING = "dw_processing"

    # Daily Wire reports PUBLISHED with settled usable media, but the episode is
    # still not marked downloadable and therefore still represents countdown media.
    PUBLISHED_WITH_COUNTDOWN = "published_with_countdown"

    # Daily Wire reports PUBLISHED with settled usable media and the episode is
    # downloadable, or WireLoft's countdown-only final safeguard has elapsed.
    PUBLISHED_FINAL = "published_final"
