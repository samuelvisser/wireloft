// Icon/label lookups for the raw snake_case status strings the backend sends
// (Episode.publishStatus, MediaDownload.downloadStatus) - not the display-label
// TS enums in types/episode.ts / types/media_download.ts, which hold pretty
// strings ("Downloaded") rather than wire values ("downloaded") and can't be
// switched on directly against API responses.

export function statusIcon(status: string) {
    switch (status) {
        case 'scheduled':
            return ['fas', 'clock'] as const
        case 'delayed':
            return ['fas', 'clock-rotate-left'] as const
        case 'live':
            return ['fas', 'circle-video'] as const
        case 'no_usable_media':
            return ['fas', 'circle-exclamation'] as const
        case 'dw_processing':
        case 'local_processing':
            return ['fas', 'spinner'] as const
        case 'published_with_countdown':
        case 'published_final':
            return ['fas', 'circle-play'] as const
        case 'downloaded':
        case 'redownloaded':
            return ['fas', 'circle-check'] as const
        case 'pending':
            return ['fas', 'clock'] as const
        case 'downloading':
            return ['fas', 'circle-down'] as const
        case 'error':
        case 'missing':
        case 'corrupted':
            return ['fas', 'circle-exclamation'] as const
        default:
            return ['fas', 'circle-exclamation'] as const
    }
}

export function statusLabel(status: string) {
    switch (status) {
        case 'scheduled':
            return 'Scheduled'
        case 'delayed':
            return 'Officially delayed'
        case 'live':
            return 'Live'
        case 'published_with_countdown':
        case 'published_final':
            return 'Published'
        case 'downloaded':
        case 'redownloaded':
            return 'Downloaded'
        case 'pending':
            return 'Queued'
        case 'downloading':
            return 'Downloading'
        case 'no_usable_media':
            return 'No usable media'
        case 'dw_processing':
            return 'Dailywire is processing the episode'
        case 'local_processing':
            return 'Locally processing the episode'
        case 'error':
            return 'Error'
        case 'missing':
            return 'File missing'
        case 'corrupted':
            return 'File corrupted'
        default:
            return 'Unknown status'
    }
}
