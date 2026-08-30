import {createSelectRegistry} from '../utils/selectRegistry';

export enum MediaDownloadStatus {
    downloaded = 'Downloaded',
    downloading = 'Downloading...',
    redownloaded = 'Redownloaded',
    localProcessing = 'Processing locally...',
    cancelled = 'Cancelled',
    error = 'Download error',
    missing = 'File missing',
    corrupted = 'File corrupted',
}

/** Wire values of a media download's downloadStatus field. */
export const MediaDownloadStatusReg = createSelectRegistry('MediaDownloadStatus', {
    'pending': {label: 'Queued', help: 'Waiting for the download worker to pick this up'},
    'downloading': {label: 'Downloading', help: 'Download in progress'},
    'downloaded': {label: 'Downloaded', help: 'Download completed'},
    'redownloaded': {label: 'Redownloaded', help: 'Episode was downloaded again'},
    'local_processing': {label: 'Processing', help: 'Processing the downloaded file locally'},
    'cancelled': {label: 'Cancelled', help: 'Stopped by the user; no replacement is queued'},
    'error': {label: 'Error', help: 'The download failed'},
    'missing': {label: 'Missing', help: 'The file watcher could not find the downloaded file on disk'},
    'corrupted': {label: 'Corrupted', help: 'The file watcher found the downloaded file, but it is empty or truncated'},
});

/** Statuses that mean a download is still in flight. */
export const ACTIVE_DOWNLOAD_STATUSES = new Set<string>(['pending', 'downloading', 'local_processing']);
