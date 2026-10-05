import type {TaskOperationRead} from '../types/schemas/operation'
import type {ProgressPresentation} from '../types/progress'
import {ACTIVE_OPERATION_STATUSES, presentDownloadProgress} from './downloadProgress'
import {waitingPresentation, workingPresentation} from './progressPresentation'
import {faIcon} from '../icons/faIcon'

export function presentOperationProgress(operation?: TaskOperationRead, starting = false): ProgressPresentation | undefined {
    if (starting && !operation) return workingPresentation('Starting')
    if (!operation || !ACTIVE_OPERATION_STATUSES.has(operation.status)) return undefined
    if (operation.kind === 'media.download') return presentDownloadProgress(undefined, operation)
    if (operation.status === 'QUEUED') return waitingPresentation('download_capacity', 'This operation is queued.')
    const wait = operation.progressMeta?.wait_state as {reason?: string; message?: string} | undefined
    if (operation.status === 'WAITING') return waitingPresentation(wait?.reason || 'dependency', wait?.message || operation.message, operation.progress ?? null)
    const batch = operation.progressMeta?.batch as {completed?: number; requested?: number; finishing?: number; failed?: number; canceled?: number} | undefined
    const isBatch = batch != null || operation.kind.includes('bulk_retry') || operation.kind.includes('redownload')
    if (operation.progress == null) return workingPresentation('Working', operation.message || 'Operation in progress.')
    const percent = Math.max(0, Math.min(99, operation.progress))
    const detail = batch
        ? `${batch.completed || 0}/${batch.requested || 0} complete; ${batch.finishing || 0} finishing; ${batch.failed || 0} failed; ${batch.canceled || 0} canceled. Work estimate, not remaining time.`
        : operation.message || 'Operation in progress.'
    return {mode: 'determinate', active: true, percent, label: `${isBatch ? '~' : ''}${percent}%`, detail,
        secondary: batch ? `${batch.completed || 0}/${batch.requested || 0} complete` : undefined,
        estimated: isBatch, icon: faIcon('fas', 'spinner'), canCancel: true, canRetry: false}
}
