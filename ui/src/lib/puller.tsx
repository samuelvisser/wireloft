import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from 'react'
import {type QueryClient, type QueryKey, useQuery, useQueryClient} from '@tanstack/react-query'
import {
  FrontendPullReadSchema,
  type FrontendPullData,
  type FrontendPullRead,
} from '../types/schemas/puller'
import {type MediaDownloadViewRead} from '../types/schemas/media_download'
import {ACTIVE_DOWNLOAD_STATUSES} from '../types/media_download'


export const FRONTEND_PULLER_QUERY_KEY = ['frontendPuller'] as const
export const FRONTEND_PULLER_SLOW_MS = 5_000
export const FRONTEND_PULLER_FAST_MS = 1_250

const DISTRIBUTED_QUERY_ROOTS = new Set([
  'operations',
  'mediaDownloadsView',
  'episodeDownloads',
  'movieDownloads',
])

type FrontendPullerContextValue = {
  snapshot: FrontendPullRead | undefined
  data: FrontendPullData | undefined
  isLoading: boolean
  error: Error | null
  refetch: () => Promise<unknown>
}

const FrontendPullerContext = createContext<FrontendPullerContextValue | null>(null)

async function fetchFrontendPuller(): Promise<FrontendPullRead> {
  const base = (window as any).appConfig?.API_URL || '/api'
  const response = await fetch(`${base}/pull`, {credentials: 'include'})
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return FrontendPullReadSchema.parse(await response.json())
}

function setDistributedQueryData(
  queryClient: QueryClient,
  queryKey: QueryKey,
  value: unknown,
) {
  queryClient.setQueryData(queryKey, value)
}

function distributeDownloads(
  queryClient: QueryClient,
  downloads: MediaDownloadViewRead[],
) {
  setDistributedQueryData(queryClient, ['mediaDownloadsView'], downloads)

  for (const [queryKey] of queryClient.getQueriesData({queryKey: ['episodeDownloads']})) {
    const episodeSlug = queryKey[1]
    if (typeof episodeSlug !== 'string') continue
    setDistributedQueryData(
      queryClient,
      queryKey,
      downloads.filter((download) => download.episodeSlug === episodeSlug),
    )
  }

  for (const [queryKey] of queryClient.getQueriesData({queryKey: ['movieDownloads']})) {
    const movieSlug = queryKey[1]
    if (typeof movieSlug !== 'string') continue
    setDistributedQueryData(
      queryClient,
      queryKey,
      downloads.filter((download) => download.movieSlug === movieSlug),
    )
  }
}

function distributeSnapshot(queryClient: QueryClient, snapshot: FrontendPullRead) {
  setDistributedQueryData(queryClient, ['operations'], snapshot.data.operations)
  distributeDownloads(queryClient, snapshot.data.mediaDownloads)
}

export function refreshFrontendPuller(queryClient: QueryClient) {
  return queryClient.invalidateQueries({queryKey: FRONTEND_PULLER_QUERY_KEY})
}

export default function FrontendPuller({children}: {children: ReactNode}) {
  const queryClient = useQueryClient()
  const refreshQueuedRef = useRef(false)
  const previousDownloadStatusesRef = useRef(new Map<number, string>())
  const query = useQuery({
    queryKey: FRONTEND_PULLER_QUERY_KEY,
    queryFn: fetchFrontendPuller,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: true,
    refetchInterval: (current) => (
      current.state.data?.mode === 'fast'
        ? FRONTEND_PULLER_FAST_MS
        : FRONTEND_PULLER_SLOW_MS
    ),
  })

  useEffect(() => {
    if (!query.data) return

    const currentStatuses = new Map<number, string>()
    for (const download of query.data.data.mediaDownloads) {
      const currentStatus = String(download.downloadStatus)
      currentStatuses.set(download.id, currentStatus)
      const previousStatus = previousDownloadStatusesRef.current.get(download.id)
      if (
        previousStatus !== undefined
        && ACTIVE_DOWNLOAD_STATUSES.has(previousStatus)
        && !ACTIVE_DOWNLOAD_STATUSES.has(currentStatus)
      ) {
        // Attempt history is a detail view rather than polling data. When the
        // shared puller observes an attempt finish, refresh an open log exactly
        // once instead of giving that dialog its own polling loop.
        void queryClient.invalidateQueries({
          queryKey: ['mediaDownloadAttempts', download.id],
          exact: true,
        })
      }
    }
    previousDownloadStatusesRef.current = currentStatuses
    distributeSnapshot(queryClient, query.data)
  }, [query.data, queryClient])

  useEffect(() => queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'invalidate') return
    const root = event.query.queryKey[0]
    if (typeof root !== 'string' || !DISTRIBUTED_QUERY_ROOTS.has(root)) return

    // Existing callers already invalidate their domain query after starting,
    // canceling or deleting work. Collapse those invalidations into one immediate
    // pull rather than teaching every caller about the transport layer.
    if (refreshQueuedRef.current) return
    refreshQueuedRef.current = true
    queueMicrotask(() => {
      refreshQueuedRef.current = false
      void refreshFrontendPuller(queryClient)
    })
  }), [queryClient])

  const value = useMemo<FrontendPullerContextValue>(() => ({
    snapshot: query.data,
    data: query.data?.data,
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error : null,
    refetch: query.refetch,
  }), [query.data, query.error, query.isLoading, query.refetch])

  return (
    <FrontendPullerContext.Provider value={value}>
      {children}
    </FrontendPullerContext.Provider>
  )
}

export function useFrontendPuller() {
  const value = useContext(FrontendPullerContext)
  if (value === null) {
    throw new Error('useFrontendPuller must be used inside FrontendPuller')
  }
  return value
}
