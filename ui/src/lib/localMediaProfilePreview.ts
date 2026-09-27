import {useEffect, useState} from 'react'

import {
    LocalMediaProfilePreviewSchema,
    type LocalMediaProfilePreview,
} from '../types/schemas/local_media_profile_preview'

type PreviewRequest = {
    type: 'show' | 'movie'
    outputTemplate: string
    preferredFormat: string
    sourceId: string
    values: Record<string, string>
    localMediaProfileId: number | null
    indexingValues: {key: string}[] | null
}

export type LocalMediaProfilePreviewState = {
    result: LocalMediaProfilePreview | null
    loading: boolean
    error: string
}

type Snapshot = {
    request: string
    result: LocalMediaProfilePreview | null
    error: string
}

export function useLocalMediaProfilePreview(request: PreviewRequest | null): LocalMediaProfilePreviewState {
    const serialized = request ? JSON.stringify(request) : null
    const [snapshot, setSnapshot] = useState<Snapshot | null>(null)

    useEffect(() => {
        if (serialized === null) return
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            try {
                const response = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/preview`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    signal: controller.signal,
                    body: serialized,
                })
                const payload = await response.json()
                if (controller.signal.aborted) return
                if (!response.ok) {
                    const detail = payload?.detail
                    setSnapshot({
                        request: serialized,
                        result: null,
                        error: typeof detail === 'string' ? detail : detail?.[0]?.msg ?? 'The profile could not be previewed.',
                    })
                    return
                }
                setSnapshot({request: serialized, result: LocalMediaProfilePreviewSchema.parse(payload), error: ''})
            } catch {
                if (!controller.signal.aborted) {
                    setSnapshot({request: serialized, result: null, error: 'The preview is temporarily unavailable.'})
                }
            }
        }, 300)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
    }, [serialized])

    // Invalidate both paths synchronously, including during the debounce delay.
    // A completed response from another example can never leak into this one.
    const current = serialized !== null && snapshot?.request === serialized
    return {
        result: current ? snapshot.result : null,
        error: current ? snapshot.error : '',
        loading: serialized !== null && !current,
    }
}
