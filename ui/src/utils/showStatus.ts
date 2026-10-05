import {faIcon} from '../icons/faIcon'
// Icon/label lookups for the raw snake_case status strings the backend sends
// (Episode.publishStatus, MediaDownload.downloadStatus) - not the display-label
// TS enums in types/episode.ts / types/media_download.ts, which hold pretty
// strings ("Downloaded") rather than wire values ("downloaded") and can't be
// switched on directly against API responses.

export function statusIcon(status: string) {
    switch (status) {
        case 'scheduled':
            return faIcon('fas', 'clock')
        case 'delayed':
            return faIcon('fas', 'clock-rotate-left')
        case 'live':
            return faIcon('fas', 'circle-video')
        case 'no_usable_media':
            return faIcon('fas', 'circle-exclamation')
        case 'dw_processing':
        case 'local_processing':
            return faIcon('fas', 'spinner')
        case 'published_with_countdown':
        case 'published_final':
            return faIcon('fas', 'circle-play')
        case 'downloaded':
        case 'redownloaded':
            return faIcon('fas', 'circle-check')
        case 'not_downloaded':
            return faIcon('fas', 'floppy-disk-circle-xmark')
        case 'pending':
            return faIcon('fas', 'clock')
        case 'downloading':
            return faIcon('fas', 'circle-down')
        case 'error':
        case 'missing':
        case 'corrupted':
            return faIcon('fas', 'circle-exclamation')
        default:
            return faIcon('fas', 'circle-exclamation')
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
        case 'not_downloaded':
            return 'Not downloaded'
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
