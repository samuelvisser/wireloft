import type {ProgressPresentation} from '../types/progress'
import {faIcon} from '../icons/faIcon'
import {formatDateTimeForDeadline} from '../utils/formatting'

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

function publicationDelayDeadline(until?: number | null): string | undefined {
    if (until == null || !Number.isFinite(until)) return undefined

    const deadline = new Date(until * 1000)
    if (Number.isNaN(deadline.getTime())) return undefined
    return formatDateTimeForDeadline(deadline)
}

export function waitingPresentation(
    reason: string,
    backendDetail?: string | null,
    percent: number | null = null,
    until?: number | null,
): ProgressPresentation {
    const value = WAITS[reason]
    const deadline = reason === 'publication_delay' ? publicationDelayDeadline(until) : undefined
    const frontendDetail = deadline && value?.[1]
        ? `${value[1]} The safety delay ends at ${deadline}.`
        : value?.[1]

    return {
        mode: 'waiting',
        active: true,
        percent,
        label: `${deadline ? `Delayed until ${deadline}` : value?.[0] || 'Waiting'}...`,
        compactLabel: reason === 'publication_delay' ? 'Delayed...' : undefined,
        detail: frontendDetail || backendDetail || 'Waiting for a dependency.',
        icon: faIcon('fass', 'clock'),
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
        icon: faIcon('fass', 'spinner'),
        canCancel: true,
        canRetry: true,
    }
}
