import {reconcileOperationSnapshots} from './operationSnapshots'
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
} from 'react'
import {type QueryClient, useQuery} from '@tanstack/react-query'
import {
  FrontendPullReadSchema,
  FrontendPullVersionSchema,
  type FrontendPullData,
  type FrontendPullRead,
} from '../types/schemas/puller'
import {usePageActive} from './pageActivity'


export const FRONTEND_PULLER_QUERY_KEY = ['frontendPuller'] as const
export const FRONTEND_PULLER_SLOW_MS = 5_000
export const FRONTEND_PULLER_FAST_MS = 1_250

const FRONTEND_APP_VERSION = import.meta.env.VITE_WIRELOFT_VERSION
let reloadRequested = false

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

function reloadIfFrontendIsOutdated(backendAppVersion: string) {
  if (reloadRequested || backendAppVersion === FRONTEND_APP_VERSION) return

  reloadRequested = true
  window.location.reload()
}

async function fetchFrontendPuller(signal?: AbortSignal): Promise<FrontendPullRead> {
  const base = (window as any).appConfig?.API_URL || '/api'
  const response = await fetch(base + '/pull', {credentials: 'include', signal})
  if (!response.ok) throw new FrontendPullError(response.status)

  const payload: unknown = await response.json()
  const {appVersion} = FrontendPullVersionSchema.parse(payload)
  reloadIfFrontendIsOutdated(appVersion)
  return FrontendPullReadSchema.parse(payload)
}

export function refreshFrontendPuller(queryClient: QueryClient) {
  return queryClient.invalidateQueries({queryKey: FRONTEND_PULLER_QUERY_KEY})
}

export default function FrontendPuller({children, onUnauthorized}: FrontendPullerProps) {
  const pageActive = usePageActive()
  const query = useQuery({
    queryKey: FRONTEND_PULLER_QUERY_KEY,
    queryFn: ({signal}) => fetchFrontendPuller(signal),
    enabled: pageActive,
    structuralSharing: (previous, incoming) => reconcileOperationSnapshots(
      previous as FrontendPullRead | undefined, incoming as FrontendPullRead,
    ),
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
