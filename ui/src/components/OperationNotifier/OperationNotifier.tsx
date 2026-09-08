import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {toast} from 'react-hot-toast'
import {type TaskOperationRead} from '../../types/schemas/operation'
import {invalidateForOperation} from '../../lib/operationInvalidation'
import {refreshFrontendPuller, useFrontendPuller} from '../../lib/puller'
import {type OperationNotificationDefinitions} from './OperationNotificationDefinitions'

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

function resultNumber(operation: TaskOperationRead, key: string): number | undefined {
  const value = operation.result?.data?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function terminalMessage(
  operation: TaskOperationRead,
  definitions: OperationNotificationDefinitions,
): string {
  const definition = definitions[operation.kind]
  const label = definition?.label || operation.title || 'Operation'

  if (operation.status === 'SUCCEEDED') {
    return definition?.success?.(operation)
      ?? operation.result?.summary
      ?? operation.message
      ?? `${operation.title} completed`
  }

  if (operation.status === 'PARTIAL') {
    if (definition?.partial) return definition.partial(operation)
    const completed = resultNumber(operation, 'completed') ?? operation.progressCurrent
    const total = resultNumber(operation, 'total') ?? operation.progressTotal
    return `${label} partially completed for ${operation.title}: ${completed}/${total} tasks succeeded`
  }

  if (operation.status === 'CANCELED') {
    if (definition?.canceled) return definition.canceled(operation)
    if (operation.message && operation.message !== 'Canceled by user') {
      return `${label} stopped for ${operation.title}: ${operation.message}`
    }
    return `${label} was canceled for ${operation.title}`
  }

  if (definition?.failed) return definition.failed(operation)
  return `${label} failed for ${operation.title}${operation.error ? `: ${operation.error}` : ''}`
}

export default function OperationNotifier({
  children,
  definitions,
}: {
  children: ReactNode
  definitions: OperationNotificationDefinitions
}) {
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
        const message = terminalMessage(operation, definitions)
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
  }, [definitions, operations, queryClient])

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
