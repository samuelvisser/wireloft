import {
  createContext,
  type ReactNode,
  useContext,
  useMemo,
} from 'react'
import {type QueryClient, useQuery} from '@tanstack/react-query'
import {
  FrontendPullReadSchema,
  type FrontendPullData,
  type FrontendPullRead,
} from '../types/schemas/puller'


export const FRONTEND_PULLER_QUERY_KEY = ['frontendPuller'] as const
export const FRONTEND_PULLER_SLOW_MS = 5_000
export const FRONTEND_PULLER_FAST_MS = 1_250

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

export function refreshFrontendPuller(queryClient: QueryClient) {
  return queryClient.invalidateQueries({queryKey: FRONTEND_PULLER_QUERY_KEY})
}

export default function FrontendPuller({children}: {children: ReactNode}) {
  const query = useQuery({
    queryKey: FRONTEND_PULLER_QUERY_KEY,
    queryFn: fetchFrontendPuller,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
    refetchInterval: (current) => (
      current.state.data?.mode === 'fast'
        ? FRONTEND_PULLER_FAST_MS
        : FRONTEND_PULLER_SLOW_MS
    ),
  })

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
