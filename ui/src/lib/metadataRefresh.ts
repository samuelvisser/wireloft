type MetadataRefreshTaskRun = {
    resourceId: number | null
    status: string
}

const METADATA_REFRESH_TASK_KEY = 'refresh_episode_metadata_worker'
const METADATA_REFRESH_POLL_INTERVAL_MS = 2000

function wait(ms: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/**
 * Wait until every task started for one manual metadata refresh request has
 * finished. Task runs are persisted, so this can distinguish a completed
 * request from one that is merely queued or running.
 */
export async function waitForMetadataRefreshCompletion(
    requestId: string,
    expectedCount: number,
): Promise<void> {
    if (expectedCount <= 0) return

    const base = (window as any).appConfig?.API_URL || '/api'
    const query = new URLSearchParams({
        definition_key: METADATA_REFRESH_TASK_KEY,
        manual_request_id: requestId,
    })

    while (true) {
        try {
            const response = await fetch(`${base}/tasks/runs?${query.toString()}`, {
                credentials: 'include',
            })
            if (!response.ok) {
                await wait(METADATA_REFRESH_POLL_INTERVAL_MS)
                continue
            }

            const runs = await response.json() as MetadataRefreshTaskRun[]
            const latestByEpisode = new Map<number, MetadataRefreshTaskRun>()

            // The API orders runs newest-first. Keep the latest row per episode
            // so an interrupted run is replaced by its startup-recovery run.
            for (const run of runs) {
                if (typeof run.resourceId !== 'number' || latestByEpisode.has(run.resourceId)) continue
                latestByEpisode.set(run.resourceId, run)
            }

            const latestRuns = Array.from(latestByEpisode.values())
            if (latestRuns.some((run) => run.status === 'FAILED')) {
                throw new Error('Metadata refresh failed')
            }

            if (
                latestRuns.length >= expectedCount
                && latestRuns.every((run) => run.status === 'SUCCEEDED')
            ) {
                return
            }
        } catch (error) {
            if (error instanceof Error && error.message === 'Metadata refresh failed') throw error
            // Keep polling through transient API errors while the task continues.
        }

        await wait(METADATA_REFRESH_POLL_INTERVAL_MS)
    }
}
