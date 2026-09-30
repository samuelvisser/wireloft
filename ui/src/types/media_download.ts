import {createSelectRegistry} from '../utils/selectRegistry';

export enum MediaDownloadStatus {
    notDownloaded = 'Not downloaded',
    downloaded = 'Downloaded',
    downloading = 'Downloading...',
    redownloaded = 'Redownloaded',
    localProcessing = 'Processing locally...',
    cancelled = 'Cancelled',
    error = 'Download error',
    missing = 'File missing',
    corrupted = 'File corrupted',
}

/** Presentation values of a media download's downloadStatus field. */
export const MediaDownloadStatusReg = createSelectRegistry('MediaDownloadStatus', {
    'not_downloaded': {label: 'Not downloaded', help: 'No file exists and no download is currently queued'},
    'pending': {label: 'Queued', help: 'Waiting for the download worker to pick this up'},
    'preparing': {label: 'Preparing', help: 'Resolving playback and planning required outputs'},
    'waiting': {label: 'Waiting', help: 'Waiting for a request or resource dependency'},
    'canceling': {label: 'Canceling', help: 'Stopping owned work before cleanup'},
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
export const ACTIVE_DOWNLOAD_STATUSES = new Set<string>(['pending', 'preparing', 'waiting', 'canceling', 'downloading', 'local_processing']);
