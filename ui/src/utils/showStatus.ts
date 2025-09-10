import type {EpisodeStatus} from '../types/show'

export function statusIcon(status: EpisodeStatus) {
    switch (status) {
        case 'scheduled':
            return ['fas', 'clock'] as const
        case 'delayed':
            return ['fas', 'clock-rotate-left'] as const
        case 'live':
            return ['fas', 'circle-video'] as const
        case 'dw_processing':
        case 'local_processing':
            return ['fas', 'spinner'] as const
        case 'published_with_countdown':
        case 'published_final':
            return ['fas', 'circle-play'] as const
        case 'downloaded':
        case 'redownloaded':
            return ['fas', 'circle-check'] as const
        case 'downloading':
            return ['fas', 'circle-down'] as const
        case 'error':
            return ['fas', 'circle-exclamation'] as const
    }
}

export function statusLabel(status: EpisodeStatus) {
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
        case 'downloading':
            return 'Downloading'
        case 'dw_processing':
            return 'Dailywire is processing the episode'
        case 'local_processing':
            return 'Locally processing the episode'
        case 'error':
            return 'Error'
    }
}