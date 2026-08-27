import {createSelectRegistry} from '../utils/selectRegistry';

export enum MediaDownloadStatus {
    downloaded = 'Downloaded',
    downloading = 'Downloading...',
    redownloaded = 'Redownloaded',
    localProcessing = 'Processing locally...',
    error = 'Download error'
}

/** Wire values of a media download's downloadStatus field. */
export const MediaDownloadStatusReg = createSelectRegistry('MediaDownloadStatus', {
    'pending': {label: 'Queued', help: 'Waiting for the download worker to pick this up'},
    'downloading': {label: 'Downloading', help: 'Download in progress'},
    'downloaded': {label: 'Downloaded', help: 'Download completed'},
    'redownloaded': {label: 'Redownloaded', help: 'Episode was downloaded again'},
    'local_processing': {label: 'Processing', help: 'Processing the downloaded file locally'},
    'error': {label: 'Error', help: 'The download failed'},
});

/** Statuses that mean a download is still in flight. */
export const ACTIVE_DOWNLOAD_STATUSES = new Set<string>(['pending', 'downloading']);
