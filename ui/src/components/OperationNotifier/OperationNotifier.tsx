import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from 'react'
import {useQueryClient, type QueryClient} from '@tanstack/react-query'
import {toast} from 'react-hot-toast'
import {type TaskOperationRead} from '../../types/schemas/operation'
import {refreshFrontendPuller, useFrontendPuller} from '../../lib/puller'

const ACTIVE_STATUSES = new Set(['QUEUED', 'RUNNING', 'WAITING'])
const TERMINAL_STATUSES = new Set(['SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELED'])

type OperationContextValue = {
  operations: TaskOperationRead[]
  findActive: (
    kind: string,
    resourceType?: string,
    resourceId?: number | null,
  ) => TaskOperationRead | undefined
}

const OperationContext = createContext<OperationContextValue>({
  operations: [],
  findActive: () => undefined,
})

async function markSeen(operationId: string): Promise<void> {
  const base = (window as any).appConfig?.API_URL || '/api'
  const response = await fetch(`${base}/operations/${encodeURIComponent(operationId)}/seen`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
}

function contextString(operation: TaskOperationRead, key: string): string | undefined {
  const value = operation.context?.[key]
  return typeof value === 'string' && value ? value : undefined
}

function resultNumber(operation: TaskOperationRead, key: string): number | undefined {
  const value = operation.result?.data?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function plural(value: number, singular: string, pluralForm = `${singular}s`) {
  return value === 1 ? singular : pluralForm
}

function operationLabel(operation: TaskOperationRead): string {
  switch (operation.kind) {
    case 'show.index':
      return 'Show indexing'
    case 'show.sync':
      return 'Sync'
    case 'show.refresh_metadata':
    case 'episode.refresh_metadata':
      return 'Metadata refresh'
    case 'show.redownload_episodes':
      return 'Re-download'
    case 'movie.refresh_extras':
      return 'Movie extra refresh'
    case 'media.download':
      return 'Download'
    default:
      return operation.title || 'Operation'
  }
}

function successMessage(operation: TaskOperationRead): string {
  const showTitle = contextString(operation, 'show_title') || operation.title

  switch (operation.kind) {
    case 'show.index': {
      const count = resultNumber(operation, 'episodes_found')
      return count === undefined
        ? `Indexing finished for ${showTitle}`
        : `Indexed ${showTitle}: ${count} ${plural(count, 'episode')} found`
    }
    case 'show.sync': {
      const count = resultNumber(operation, 'episodes_found') ?? 0
      return `Sync finished for ${showTitle}: ${count} new ${plural(count, 'episode')} found`
    }
    case 'show.refresh_metadata': {
      const count = operation.progressTotal
      return count === 0
        ? `No episodes to refresh in ${showTitle}`
        : `Metadata refresh completed for ${count} ${plural(count, 'episode')} in ${showTitle}`
    }
    case 'episode.refresh_metadata': {
      const episodeTitle = contextString(operation, 'episode_title') || operation.title
      return `Metadata refresh completed for ${episodeTitle}`
    }
    case 'show.redownload_episodes': {
      const files = resultNumber(operation, 'episode_files') ?? 0
      const profiles = resultNumber(operation, 'download_profiles')
      const profileDetail = profiles === undefined
        ? ''
        : ` using ${profiles} ${plural(profiles, 'Download Profile')}`
      return `Re-download finished for ${showTitle}: ${files} episode ${plural(files, 'file')} re-downloaded${profileDetail}`
    }
    case 'media.download':
      return operation.result?.summary || `Downloaded ${operation.title}`
    default:
      return operation.result?.summary || operation.message || `${operation.title} completed`
  }
}

function terminalMessage(operation: TaskOperationRead): string {
  if (operation.status === 'SUCCEEDED') return successMessage(operation)

  const label = operationLabel(operation)
  if (operation.status === 'PARTIAL') {
    const completed = resultNumber(operation, 'completed') ?? operation.progressCurrent
    const total = resultNumber(operation, 'total') ?? operation.progressTotal
    return `${label} partially completed for ${operation.title}: ${completed}/${total} tasks succeeded`
  }
  if (operation.status === 'CANCELED') {
    if (operation.message && operation.message !== 'Canceled by user') {
      return `${label} stopped for ${operation.title}: ${operation.message}`
    }
    return `${label} was canceled for ${operation.title}`
  }
  return `${label} failed for ${operation.title}${operation.error ? `: ${operation.error}` : ''}`
}

function taskLedgerQueryMatchesOperation(queryKey: readonly unknown[], operation: TaskOperationRead): boolean {
  if (queryKey[0] !== 'taskLedger') return false

  const resourceType = queryKey[2]
  if (resourceType !== undefined && resourceType !== operation.resourceType) return false

  const resourceFilter = queryKey[3]
  if (resourceFilter === undefined || operation.resourceId == null) return true
  if (typeof resourceFilter === 'number') return resourceFilter === operation.resourceId
  return Array.isArray(resourceFilter) && resourceFilter.includes(operation.resourceId)
}

async function invalidateForOperation(queryClient: QueryClient, operation: TaskOperationRead) {
  const showSlug = contextString(operation, 'show_slug')
  const episodeSlug = contextString(operation, 'episode_slug')
  const movieSlug = contextString(operation, 'movie_slug')
  const invalidations: Promise<unknown>[] = [
    queryClient.invalidateQueries({
      predicate: (query) => taskLedgerQueryMatchesOperation(query.queryKey, operation),
    }),
  ]

  if (operation.kind.startsWith('show.')) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['shows']}),
      queryClient.invalidateQueries({queryKey: ['showsView']}),
    )
    if (showSlug) {
      invalidations.push(
        queryClient.invalidateQueries({queryKey: ['show', showSlug]}),
        queryClient.invalidateQueries({queryKey: ['episodes', showSlug]}),
      )
    }
  }

  if (operation.kind === 'show.redownload_episodes') {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}))
  }

  if (operation.kind === 'episode.refresh_metadata') {
    if (episodeSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episode', episodeSlug]}))
    }
    if (showSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episodes', showSlug]}))
    }
  }

  if (operation.kind.startsWith('movie.')) {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['movies']}))
    if (movieSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['dailywireMovie', movieSlug]}))
    }
  }

  if (operation.kind === 'media.download') {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}))
    if (episodeSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episode', episodeSlug]}))
    }
    if (showSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episodes', showSlug]}))
    }
    if (movieSlug) {
      invalidations.push(
        queryClient.invalidateQueries({queryKey: ['movies']}),
        queryClient.invalidateQueries({queryKey: ['dailywireMovie', movieSlug]}),
      )
    }
  }

  await Promise.all(invalidations)
}

export default function OperationNotifier({children}: {children: ReactNode}) {
  const queryClient = useQueryClient()
  const handledRef = useRef(new Set<string>())
  const previousActiveRef = useRef(new Map<string, TaskOperationRead>())
  const {data: pullData} = useFrontendPuller()
  const operations = pullData?.operations ?? []

  // If another browser acknowledges a terminal operation before this browser
  // observes the terminal snapshot, it disappears from the pull. Remembering the
  // active snapshot still lets this browser refresh the affected ordinary queries.
  useEffect(() => {
    if (!pullData) return

    const currentById = new Map(operations.map((operation) => [operation.id, operation]))
    const currentActive = new Map(
      operations
        .filter((operation) => ACTIVE_STATUSES.has(operation.status))
        .map((operation) => [operation.id, operation]),
    )

    for (const [operationId, previous] of previousActiveRef.current) {
      if (currentActive.has(operationId) || currentById.has(operationId)) continue
      void invalidateForOperation(queryClient, previous)
    }
    previousActiveRef.current = currentActive
  }, [operations, pullData, queryClient])

  // Every terminal operation stays in the generic pull until a frontend has
  // processed the domain-data refresh it implies. UI operations additionally get
  // a toast; automated/API work is acknowledged silently after invalidation.
  useEffect(() => {
    for (const operation of operations) {
      if (
        !TERMINAL_STATUSES.has(operation.status)
        || handledRef.current.has(operation.id)
      ) {
        continue
      }

      handledRef.current.add(operation.id)
      if (operation.source === 'UI' && !operation.notificationSeenAt) {
        const message = terminalMessage(operation)
        if (operation.status === 'SUCCEEDED') {
          toast.success(message, {duration: 5000})
        } else if (operation.status === 'PARTIAL' || operation.status === 'CANCELED') {
          toast(message, {duration: 6000})
        } else {
          toast.error(message, {duration: 6000})
        }
      }

      void (async () => {
        try {
          await invalidateForOperation(queryClient, operation)
          if (!operation.notificationSeenAt) {
            await markSeen(operation.id)
            await refreshFrontendPuller(queryClient)
          }
        } catch {
          // Leave an unacknowledged operation durable server-side so a later
          // browser reload can retry the cache refresh/acknowledgement path.
        }
      })()
    }
  }, [operations, queryClient])

  const value = useMemo<OperationContextValue>(() => ({
    operations,
    findActive: (kind, resourceType, resourceId) => operations.find((operation) => (
      ACTIVE_STATUSES.has(operation.status)
      && operation.kind === kind
      && (resourceType === undefined || operation.resourceType === resourceType)
      && (resourceId === undefined || operation.resourceId === resourceId)
    )),
  }), [operations])

  return (
    <OperationContext.Provider value={value}>
      {children}
    </OperationContext.Provider>
  )
}

export function useOperations() {
  return useContext(OperationContext)
}

export function useActiveOperation(
  kind: string,
  resourceType?: string,
  resourceId?: number | null,
) {
  const {findActive} = useOperations()
  if (resourceId === null) return undefined
  return findActive(kind, resourceType, resourceId)
}
