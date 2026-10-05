import type {ProgressPresentation} from '../types/progress'
import {faIcon} from '../icons/faIcon'

const WAITS: Record<string, [string, string]> = {
    daily_wire_request_cooldown: ['Cooldown', 'Waiting for The Daily Wire request cooldown. The operation will resume automatically.'],
    daily_wire_request_queue: ['API queue', 'Waiting for a turn to request The Daily Wire.'],
    request_spacing: ['Waiting', 'Waiting for the next permitted API request.'],
    upstream_retry: ['Retry wait', 'The server requested a delay before retrying.'],
    retry_backoff: ['Retry wait', 'Waiting before retrying the network request.'],
    download_capacity: ['Queued', 'Waiting for an available media download slot.'],
    sidecar_capacity: ['Asset queue', 'Waiting for an auxiliary download slot.'],
    processing_capacity: ['Processing queue', 'Waiting for a local processing slot.'],
    custom_indexes: ['Preparing...', 'Waiting for Custom Index assignments.'],
    previous_attempt: ['Restarting', 'Waiting for the previous download to stop and clean up.'],
    publication_delay: ['Delayed', 'Waiting for the post-publication safety delay before downloading.'],
}

export function waitingPresentation(
    reason: string,
    detail?: string | null,
    percent: number | null = null,
): ProgressPresentation {
    const value = WAITS[reason]
    return {
        mode: 'waiting',
        active: true,
        percent,
        label: `${value?.[0] || 'Waiting'}...`,
        detail: detail || value?.[1] || 'Waiting for a dependency.',
        icon: faIcon('fas', 'clock'),
        canCancel: true,
        canRetry: true,
    }
}

export function workingPresentation(
    label = 'Preparing',
    detail = label,
    compactLabel = label,
): ProgressPresentation {
    return {
        mode: 'indeterminate',
        active: true,
        percent: null,
        label: `${label}...`,
        compactLabel: `${compactLabel}...`,
        detail,
        icon: faIcon('fas', 'spinner'),
        canCancel: true,
        canRetry: true,
    }
}
