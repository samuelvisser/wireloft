import {useEffect, useState} from 'react'

import {
    CustomIndexAdvisoryResultSchema,
    type CustomIndexAdvisoryResult,
} from '../types/schemas/output_template_advisory'

type Snapshot = {
    request: string
    result: CustomIndexAdvisoryResult | null
}

/** Independent of preview requests: advice must never delay rendering or saving. */
export function useCustomIndexAdvisory(request: string | null) {
    const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
    useEffect(() => {
        if (request === null) return
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            try {
                const response = await fetch(
                    `${(window as any).appConfig.API_URL}/local-media-profiles/advisory/custom-index`,
                    {
                        method: 'POST',
                        credentials: 'include',
                        headers: {'Content-Type': 'application/json'},
                        signal: controller.signal,
                        body: request,
                    },
                )
                if (!response.ok) throw new Error('Advisory request failed')
                const result = CustomIndexAdvisoryResultSchema.parse(await response.json())
                if (!controller.signal.aborted) setSnapshot({request, result})
            } catch {
                if (!controller.signal.aborted) setSnapshot({request, result: null})
            }
        }, 300)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
    }, [request])

    // Hide outdated diagnostics as soon as the template/definitions change.
    // In particular, a stale suggestion must never overwrite newer typing.
    const current = request !== null && snapshot?.request === request
    return {
        advisories: current ? snapshot.result?.advisories ?? [] : [],
        unavailable: current && snapshot.result === null,
    }
}
