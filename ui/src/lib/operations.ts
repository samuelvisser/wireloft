import {useCallback} from 'react'
import {useQueryClient} from '@tanstack/react-query'

export type OperationAccepted = {
    operationId: string
    [key: string]: unknown
}

export type OperationControlAction = 'cancel' | 'restart'

export class OperationStartError extends Error {
    readonly status: number

    constructor(message: string, status: number) {
        super(message)
        this.name = 'OperationStartError'
        this.status = status
    }
}

export class OperationControlError extends Error {
    readonly status: number

    constructor(message: string, status: number) {
        super(message)
        this.name = 'OperationControlError'
        this.status = status
    }
}

async function responseError(response: Response): Promise<string> {
    try {
        const body = await response.json()
        if (typeof body?.detail === 'string' && body.detail.trim()) return body.detail
    } catch {
        // Fall back to the HTTP status below.
    }
    return `HTTP ${response.status}`
}

/**
 * Start a backend TaskOperation and register it with the global notifier.
 *
 * Action components only need to own their confirmation UI and action-specific
 * request payload. Correlation, polling, progress, completion, retries, query
 * refreshes and durable notifications all belong to the operation subsystem.
 */
export function useStartOperation() {
    const queryClient = useQueryClient()

    return useCallback(async <T extends OperationAccepted = OperationAccepted>(
        url: string,
        init: RequestInit = {},
    ): Promise<T> => {
        const response = await fetch(url, {
            credentials: 'include',
            ...init,
        })
        if (!response.ok) {
            throw new OperationStartError(await responseError(response), response.status)
        }

        const result = await response.json() as T
        if (typeof result?.operationId !== 'string' || !result.operationId) {
            throw new OperationStartError(
                'Operation request did not return an operation ID',
                response.status,
            )
        }

        // The endpoint has committed the durable operation by the time it
        // returns. Pull it into OperationNotifier immediately instead of waiting
        // for the idle discovery heartbeat.
        await queryClient.invalidateQueries({queryKey: ['operations']})
        return result
    }, [queryClient])
}

/** Cancel or restart an existing durable TaskOperation. */
export function useControlOperation() {
    const queryClient = useQueryClient()

    return useCallback(async (
        operationId: string,
        action: OperationControlAction,
    ): Promise<void> => {
        const base = (window as any).appConfig?.API_URL || '/api'
        const response = await fetch(
            `${base}/operations/${encodeURIComponent(operationId)}/${action}`,
            {method: 'POST', credentials: 'include'},
        )
        if (!response.ok) {
            throw new OperationControlError(await responseError(response), response.status)
        }

        await queryClient.invalidateQueries({queryKey: ['operations']})
    }, [queryClient])
}
