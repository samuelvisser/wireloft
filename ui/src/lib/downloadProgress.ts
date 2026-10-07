import type {MediaDownloadDomainViewRead} from '../types/schemas/media_download'
import type {TaskOperationRead} from '../types/schemas/operation'
import type {DownloadPresentation, ProgressPresentation} from '../types/progress'
import {DownloadExecutionSchema, type DownloadExecution, type DownloadStage} from '../types/schemas/download_execution'
import {formatBytes, formatDate} from '../utils/formatting'
import {waitingPresentation, workingPresentation} from './progressPresentation'
import {faIcon} from '../icons/faIcon'

export const ACTIVE_OPERATION_STATUSES = new Set(['QUEUED', 'RUNNING', 'WAITING'])

type DownloadWaitState = {
    reason?: string
    message?: string
    until?: number | null
}

function publicationDelayLabels(wait: DownloadWaitState): {label: string; compactLabel: string} | undefined {
    if (wait.reason !== 'publication_delay' || wait.until == null || !Number.isFinite(wait.until)) return undefined

    const until = new Date(wait.until * 1000)
    if (Number.isNaN(until.getTime())) return undefined

    return {
        label: `Delayed until ${formatDate(until)}...`,
        compactLabel: 'Delayed...',
    }
}

const ACTIVITIES: Record<string, string> = {
    prepare: 'Preparing', authorize: 'Authorizing', resolve_playback: 'Resolving playback',
    inspect_stream: 'Inspecting stream', plan_outputs: 'Preparing outputs',
    download_media: 'Downloading', remux: 'Remuxing media', convert_audio: 'Converting video to M4A',
    embed_artwork: 'Embedding thumbnail', embed_metadata: 'Embedding metadata',
    embed_artwork_metadata: 'Embedding artwork and metadata',
    publish_media: 'Moving media into the library', verify: 'Verifying files', finalize: 'Finalizing',
}
export function downloadExecution(operation?: TaskOperationRead): DownloadExecution | undefined {
    const parsed = DownloadExecutionSchema.safeParse(operation?.progressMeta?.download)
    return parsed.success ? parsed.data : undefined
}

export function activityLabel(stage: Pick<DownloadStage, 'code' | 'asset_id'>): string {
    const asset = stage.asset_id === 'artwork' ? 'thumbnail' : stage.asset_id === 'nfo' ? 'NFO metadata' : 'sidecar'
    if (stage.code === 'download_sidecar') return `Downloading ${asset}`
    if (stage.code === 'generate_sidecar') return `Generating ${asset}`
    if (stage.code === 'publish_sidecar') return `Publishing ${asset}`
    return ACTIVITIES[stage.code] || 'Processing'
}

function terminal(status: string, label: string, detail: string, outcome?: ProgressPresentation['outcome']): DownloadPresentation {
    return {
        status, mode: 'terminal', active: false, percent: null, label, detail, outcome,
        icon: faIcon('fas', outcome === 'success' ? 'circle-check' : outcome === 'error' ? 'triangle-exclamation' : 'download'),
        canCancel: false, canRetry: status !== 'not_downloaded',
    }
}

export function isPublicationDelayWait(operation?: TaskOperationRead): boolean {
    if (operation?.status !== 'WAITING') return false

    const execution = downloadExecution(operation)
    const main = execution?.stages.find(stage => stage.id === execution.main_activity)
    const wait = (main?.wait || operation.progressMeta?.wait_state) as DownloadWaitState | undefined
    return wait?.reason === 'publication_delay'
}

export function presentDownloadProgress(download?: MediaDownloadDomainViewRead, operation?: TaskOperationRead, starting = false): DownloadPresentation {
    if (starting) return {status: 'preparing', ...workingPresentation('Starting', 'Starting the requested download.')}
    if (operation && ACTIVE_OPERATION_STATUSES.has(operation.status)) {
        const execution = downloadExecution(operation)
        if (operation.progressMeta?.canceling === true || operation.context?.cancel_requested === true || execution?.canceling) {
            return {status: 'canceling', ...workingPresentation('Canceling', 'Stopping the download and its owned auxiliary work before cleaning up.'), canCancel: false, canRetry: false}
        }
        if (operation.status === 'QUEUED') return {status: 'pending', ...waitingPresentation('download_capacity'), canRetry: false}
        const main = execution?.stages.find(stage => stage.id === execution.main_activity)
        const media = execution?.stages.find(stage => stage.id === 'media')
        const transferPercent = execution?.phase === 'transferring' && main?.id === 'media' && media?.fraction != null
            ? Math.max(0, Math.min(100, Math.floor(media.fraction * 100))) : null
        const wait = (main?.wait || operation.progressMeta?.wait_state) as DownloadWaitState | undefined
        if (wait?.reason) return {
            status: 'waiting',
            ...waitingPresentation(wait.reason, wait.message, transferPercent),
            ...(publicationDelayLabels(wait) || {}),
        }
        if (operation.status === 'WAITING') return {status: 'waiting', ...waitingPresentation('dependency', operation.message, transferPercent)}
        const secondary = execution?.stages.filter(stage => stage.id !== main?.id && ['running', 'waiting'].includes(stage.state))
            .map(stage => stage.wait ? `${activityLabel(stage)}: waiting` : activityLabel(stage)).join(' / ')
        if (execution?.phase === 'transferring' && main?.id === 'media') {
            const audioOnly = download?.preferredFormat === 'format_audio_only'
            const basis = media?.segments_total
                ? `${media.segments_done || 0}/${media.segments_total} media segments`
                : media?.total_bytes
                    ? audioOnly
                        ? `${formatBytes(media.bytes_received)} / ${formatBytes(media.total_bytes)} downloaded`
                        : `${media.bytes_received.toLocaleString()}/${media.total_bytes.toLocaleString()} bytes`
                    : audioOnly
                        ? `${formatBytes(media?.bytes_received ?? 0)} downloaded; total size unknown`
                        : `${media?.bytes_received?.toLocaleString() || '0'} bytes received; total size unknown`
            if (transferPercent !== null) return {status: 'downloading', mode: 'determinate', active: true, percent: transferPercent,
                label: `${transferPercent}%`, detail: `Primary media transfer: ${basis}.`, icon: faIcon('fas', 'download'), secondary,
                canCancel: true, canRetry: true}
            return {status: 'downloading', ...workingPresentation('Downloading', basis), secondary}
        }
        const compact = main?.code.startsWith('embed') ? 'Embedding' : main?.code.startsWith('publish') ? 'Publishing'
            : execution?.phase === 'preparing' ? 'Preparing' : main ? activityLabel(main) : 'Preparing'
        const label = main?.id === 'media' && execution?.primary_transfer_complete ? 'Finishing' : main ? activityLabel(main) : 'Preparing'
        return {status: execution?.primary_transfer_complete ? 'local_processing' : 'preparing',
            ...workingPresentation(label, `${label}.`, compact), secondary}
    }
    if (operation?.status === 'SUCCEEDED') return terminal(operation.context?.is_redownload ? 'redownloaded' : 'downloaded', 'Downloaded', 'All required outputs were published successfully.', 'success')
    if (operation?.status === 'FAILED' || operation?.status === 'PARTIAL') return terminal('error', 'Failed', operation.error || operation.message || 'Download failed.', 'error')
    if (operation?.status === 'CANCELED') return terminal('cancelled', 'Canceled', 'The download was canceled.', 'canceled')
    if (download?.artifactStatus === 'available') return terminal(download.latestTaskIsRedownload ? 'redownloaded' : 'downloaded', 'Downloaded', 'The media file is available.', 'success')
    if (download?.artifactStatus === 'missing') return terminal('missing', 'Missing', 'The downloaded file could not be found.', 'error')
    if (download?.artifactStatus === 'corrupted') return terminal('corrupted', 'Corrupted', download.artifactError || 'The downloaded file failed verification.', 'error')
    if (download?.latestTaskStatus === 'RUNNING') return {status: 'preparing', ...workingPresentation('Preparing', 'Waiting for the current execution snapshot.')}
    if (download?.latestTaskStatus === 'FAILED') return terminal('error', 'Failed', download.latestTaskError || 'Download failed.', 'error')
    if (download?.automaticRetrySuppressed || download?.latestTaskStatus === 'CANCELED') return terminal('cancelled', 'Canceled', 'No automatic replacement is queued.', 'canceled')
    return terminal('not_downloaded', 'Not downloaded', 'No download is currently queued.')
}
