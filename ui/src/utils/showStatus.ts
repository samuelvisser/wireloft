import {EpisodePublishStatus} from "../types/episode";
import {MediaDownloadStatus} from "../types/media_download";


export function statusIcon(status: EpisodePublishStatus | MediaDownloadStatus | string) {
    switch (status) {
        case EpisodePublishStatus.scheduled:
            return ['fas', 'clock'] as const
        case EpisodePublishStatus.delayed:
            return ['fas', 'clock-rotate-left'] as const
        case EpisodePublishStatus.live:
            return ['fas', 'circle-video'] as const
        case EpisodePublishStatus.dwProcessing:
        case MediaDownloadStatus.localProcessing:
            return ['fas', 'spinner'] as const
        case EpisodePublishStatus.publishedWithCountdown:
        case EpisodePublishStatus.publishedFinal:
            return ['fas', 'circle-play'] as const
        case MediaDownloadStatus.downloaded:
        case MediaDownloadStatus.redownloaded:
            return ['fas', 'circle-check'] as const
        case MediaDownloadStatus.downloading:
            return ['fas', 'circle-down'] as const
        case MediaDownloadStatus.error:
            return ['fas', 'circle-exclamation'] as const
        default:
            return ['fas', 'circle-exclamation'] as const
    }
}

export function statusLabel(status: EpisodePublishStatus | MediaDownloadStatus | string) {
    switch (status) {
        case EpisodePublishStatus.scheduled:
            return 'Scheduled'
        case EpisodePublishStatus.delayed:
            return 'Officially delayed'
        case EpisodePublishStatus.live:
            return 'Live'
        case EpisodePublishStatus.publishedWithCountdown:
        case EpisodePublishStatus.publishedFinal:
            return 'Published'
        case MediaDownloadStatus.downloaded:
        case MediaDownloadStatus.redownloaded:
            return 'Downloaded'
        case MediaDownloadStatus.downloading:
            return 'Downloading'
        case EpisodePublishStatus.dwProcessing:
            return 'Dailywire is processing the episode'
        case MediaDownloadStatus.localProcessing:
            return 'Locally processing the episode'
        case MediaDownloadStatus.error:
            return 'Error'
        default:
            return 'Unknown error'
    }
}