import type {FrontendPullRead} from '../types/schemas/puller'
import type {TaskOperationRead} from '../types/schemas/operation'
import {downloadExecution} from './downloadProgress'

function timestamp(value?: string | null): number {
    return value ? Date.parse(value) || 0 : 0
}

/** Keep removals authoritative; only reject stale updates for the same operation. */
export function reconcileOperationSnapshots(previous: FrontendPullRead | undefined, incoming: FrontendPullRead): FrontendPullRead {
    if (!previous) return incoming
    const prior = new Map(previous.data.operations.map(operation => [operation.id, operation]))
    return {...incoming, data: {...incoming.data, operations: incoming.data.operations.map(operation => {
        const old = prior.get(operation.id)
        return old && isOlder(operation, old) ? old : operation
    })}}
}

function isOlder(incoming: TaskOperationRead, previous: TaskOperationRead): boolean {
    const nextExecution = downloadExecution(incoming)
    const oldExecution = downloadExecution(previous)
    if (nextExecution && oldExecution) {
        if (nextExecution.attempt_id === oldExecution.attempt_id) {
            return nextExecution.sequence < oldExecution.sequence
        }
        if (nextExecution.started_at !== oldExecution.started_at) {
            return nextExecution.started_at < oldExecution.started_at
        }
    }
    // Terminal updates have no active execution payload. Their database timestamp
    // must win over an earlier transfer snapshot, including its last 100% reading.
    return timestamp(incoming.updatedAt) < timestamp(previous.updatedAt)
}
