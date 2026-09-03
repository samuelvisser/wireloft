type ShowRedownloadTaskRun = {
    status: string
}

const SHOW_REDOWNLOAD_TASK_KEY = 'redownload_show_episodes_worker'
const SHOW_REDOWNLOAD_POLL_INTERVAL_MS = 2000

function wait(ms: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/** Wait for the durable master task created by a manual show re-download request. */
export async function waitForShowRedownloadCompletion(requestId: string): Promise<void> {
    const base = (window as any).appConfig?.API_URL || '/api'
    const query = new URLSearchParams({
        definition_key: SHOW_REDOWNLOAD_TASK_KEY,
        manual_request_id: requestId,
    })

    while (true) {
        try {
            const response = await fetch(`${base}/tasks/runs?${query.toString()}`, {
                credentials: 'include',
            })
            if (!response.ok) {
                await wait(SHOW_REDOWNLOAD_POLL_INTERVAL_MS)
                continue
            }

            const runs = await response.json() as ShowRedownloadTaskRun[]
            const latest = runs[0]
            if (!latest) {
                await wait(SHOW_REDOWNLOAD_POLL_INTERVAL_MS)
                continue
            }
            if (latest.status === 'FAILED' || latest.status === 'CANCELED') {
                throw new Error('Show re-download failed')
            }
            if (latest.status === 'SUCCEEDED') return
        } catch (error) {
            if (error instanceof Error && error.message === 'Show re-download failed') throw error
            // Keep polling through transient API failures while the worker runs.
        }

        await wait(SHOW_REDOWNLOAD_POLL_INTERVAL_MS)
    }
}
