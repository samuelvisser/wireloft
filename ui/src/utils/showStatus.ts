import type {EpisodeStatus} from '../types/show'

export function statusIcon(status: EpisodeStatus) {
    switch (status) {
        case 'scheduled':
            return ['fas', 'clock'] as const
        case 'live':
            return ['fas', 'circle-play'] as const
        case 'downloaded':
            return ['fas', 'circle-check'] as const
        case 'downloading':
            return ['fas', 'arrow-down'] as const
        case 'dw_processing':
        case 'local_processing':
            return ['fas', 'spinner'] as const
        case 'error':
            return ['fas', 'circle-exclamation'] as const
    }
}

export function statusLabel(status: EpisodeStatus) {
    switch (status) {
        case 'downloaded':
            return 'Downloaded'
        case 'downloading':
            return 'Downloading'
        case 'dw_processing':
        case 'local_processing':
            return 'Waiting for processing'
        case 'error':
            return 'Error'
    }
}