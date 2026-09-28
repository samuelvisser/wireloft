import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
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

type FrontendPullerProps = {
  children: ReactNode
  onUnauthorized?: () => void
}

class FrontendPullError extends Error {
  constructor(readonly status: number) {
    super('HTTP ' + status)
  }
}

const FrontendPullerContext = createContext<FrontendPullerContextValue | null>(null)

function isForeground() {
  return document.visibilityState === 'visible' && document.hasFocus()
}

function subscribeToForeground(onChange: () => void) {
  window.addEventListener('focus', onChange)
  window.addEventListener('blur', onChange)
  document.addEventListener('visibilitychange', onChange)
  return () => {
    window.removeEventListener('focus', onChange)
    window.removeEventListener('blur', onChange)
    document.removeEventListener('visibilitychange', onChange)
  }
}

async function fetchFrontendPuller(signal?: AbortSignal): Promise<FrontendPullRead> {
  const base = (window as any).appConfig?.API_URL || '/api'
  const response = await fetch(base + '/pull', {credentials: 'include', signal})
  if (!response.ok) throw new FrontendPullError(response.status)
  return FrontendPullReadSchema.parse(await response.json())
}

export function refreshFrontendPuller(queryClient: QueryClient) {
  return queryClient.invalidateQueries({queryKey: FRONTEND_PULLER_QUERY_KEY})
}

export default function FrontendPuller({children, onUnauthorized}: FrontendPullerProps) {
  const foreground = useSyncExternalStore(subscribeToForeground, isForeground, () => false)
  const query = useQuery({
    queryKey: FRONTEND_PULLER_QUERY_KEY,
    queryFn: ({signal}) => fetchFrontendPuller(signal),
    enabled: foreground,
    staleTime: 0,
    retry: false,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: false,
    refetchInterval: (current) => {
      if (current.state.error instanceof FrontendPullError && current.state.error.status === 401) {
        return false
      }
      return current.state.data?.mode === 'fast'
        ? FRONTEND_PULLER_FAST_MS
        : FRONTEND_PULLER_SLOW_MS
    },
  })

  useEffect(() => {
    if (query.error instanceof FrontendPullError && query.error.status === 401) {
      onUnauthorized?.()
    }
  }, [onUnauthorized, query.error])

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
