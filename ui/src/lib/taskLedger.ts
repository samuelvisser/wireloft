import {type InfiniteData, type QueryClient} from '@tanstack/react-query'
import {
  contiguousLazyCollectionItems,
  type LazyCollectionPage,
  type LazyCollectionPageRequest,
  useLazyCollection,
} from './lazyCollection'
import {
  TaskLedgerPageReadSchema,
  type TaskLedgerEntryRead,
  type TaskLedgerPageRead,
} from '../types/schemas/task'
import {usePageActive} from './pageActivity'

export type TaskLedgerCollectionQuery = {
  definitionKey?: string
  resourceType?: string
  resourceId?: number | readonly number[]
  status?: readonly string[]
  startedAfter?: Date | string
  orderBy?: 'started_at' | 'finished_at' | 'created_at'
  order?: 'asc' | 'desc'
  limit?: number
  enabled?: boolean
}

function normalizeResourceIds(value: TaskLedgerCollectionQuery['resourceId']): number[] | undefined {
  if (value === undefined) return undefined
  const values = typeof value === 'number' ? [value] : [...value]
  return [...new Set(values)].sort((left, right) => left - right)
}

function normalizeStatuses(value: TaskLedgerCollectionQuery['status']): string[] | undefined {
  if (value === undefined) return undefined
  return [...new Set(value)].sort()
}

function normalizeStartedAfter(value: TaskLedgerCollectionQuery['startedAfter']): string | undefined {
  if (value === undefined) return undefined
  return value instanceof Date ? value.toISOString() : value
}

function optionalScalarFilterContains(source: unknown, target: string | undefined): boolean {
  if (target === undefined) return source === null
  return source === null || source === target
}

function optionalArrayFilterContains<T extends string | number>(
  source: unknown,
  target: readonly T[] | undefined,
): boolean {
  if (target === undefined) return source === null
  if (source === null) return true
  if (!Array.isArray(source)) return false
  const sourceValues = new Set(source)
  return target.every((value) => sourceValues.has(value))
}

function startedAfterFilterContains(source: unknown, target: string | undefined): boolean {
  if (target === undefined) return source === null
  if (source === null) return true
  if (typeof source !== 'string') return false

  const sourceTime = Date.parse(source)
  const targetTime = Date.parse(target)
  if (Number.isNaN(sourceTime) || Number.isNaN(targetTime)) return source === target
  return sourceTime <= targetTime
}

function taskLedgerEntryMatches(
  entry: TaskLedgerEntryRead,
  {
    definitionKey,
    resourceType,
    resourceIds,
    statuses,
    startedAfter,
  }: {
    definitionKey: string | undefined
    resourceType: string | undefined
    resourceIds: readonly number[] | undefined
    statuses: readonly string[] | undefined
    startedAfter: string | undefined
  },
): boolean {
  if (definitionKey !== undefined && entry.definitionKey !== definitionKey) return false
  if (resourceType !== undefined && entry.resourceType !== resourceType) return false
  if (
    resourceIds !== undefined
    && (entry.resourceId == null || !resourceIds.includes(entry.resourceId))
  ) {
    return false
  }
  if (statuses !== undefined && !statuses.includes(entry.status)) return false
  if (startedAfter !== undefined) {
    if (!entry.startedAt) return false
    const startedAt = Date.parse(entry.startedAt)
    const threshold = Date.parse(startedAfter)
    if (
      Number.isNaN(startedAt)
      || Number.isNaN(threshold)
      || startedAt < threshold
    ) {
      return false
    }
  }
  return true
}

export function deriveTaskLedgerCollectionPlaceholder(
  queryClient: QueryClient,
  {
    definitionKey,
    resourceType,
    resourceIds,
    statuses,
    startedAfter,
    orderBy,
    order,
    initialCount,
  }: {
    definitionKey: string | undefined
    resourceType: string | undefined
    resourceIds: readonly number[] | undefined
    statuses: readonly string[] | undefined
    startedAfter: string | undefined
    orderBy: 'started_at' | 'finished_at' | 'created_at'
    order: 'asc' | 'desc'
    initialCount: number
  },
): InfiniteData<
  LazyCollectionPage<TaskLedgerEntryRead>,
  LazyCollectionPageRequest
> | undefined {
  const targetDescriptor = [
    definitionKey ?? null,
    resourceType ?? null,
    resourceIds ?? null,
    statuses ?? null,
    startedAfter ?? null,
    orderBy,
    order,
  ]
  const candidates = queryClient.getQueryCache().findAll({
    queryKey: ['taskLedger', 'list'],
  })

  let best: {
    data: InfiniteData<
      LazyCollectionPage<TaskLedgerEntryRead>,
      LazyCollectionPageRequest
    >
    matchCount: number
    updatedAt: number
  } | undefined

  for (const query of candidates) {
    const key = query.queryKey
    if (
      key[0] !== 'taskLedger'
      || key[1] !== 'list'
      || key[7] !== orderBy
      || key[8] !== order
      || !optionalScalarFilterContains(key[2], definitionKey)
      || !optionalScalarFilterContains(key[3], resourceType)
      || !optionalArrayFilterContains(key[4], resourceIds)
      || !optionalArrayFilterContains(key[5], statuses)
      || !startedAfterFilterContains(key[6], startedAfter)
    ) {
      continue
    }

    const sourceDescriptor = key.slice(2, 9)
    if (JSON.stringify(sourceDescriptor) === JSON.stringify(targetDescriptor)) continue

    const source = query.state.data as InfiniteData<
      LazyCollectionPage<TaskLedgerEntryRead>,
      LazyCollectionPageRequest
    > | undefined
    if (!source?.pages.length) continue

    const contiguous = contiguousLazyCollectionItems(source.pages)
    if (!contiguous) continue

    const matching = contiguous.items.filter((entry) => taskLedgerEntryMatches(
      entry,
      {
        definitionKey,
        resourceType,
        resourceIds,
        statuses,
        startedAfter,
      },
    ))
    if (matching.length === 0 && !contiguous.complete) continue

    const items = matching.slice(0, initialCount)
    const total = contiguous.complete ? matching.length : items.length
    const placeholder: InfiniteData<
      LazyCollectionPage<TaskLedgerEntryRead>,
      LazyCollectionPageRequest
    > = {
      pages: [{
        items,
        total,
        offset: 0,
        limit: initialCount,
        hasMore: !contiguous.complete || items.length < matching.length,
      }],
      pageParams: [{offset: 0, limit: initialCount}],
    }

    if (
      best === undefined
      || items.length > best.matchCount
      || (
        items.length === best.matchCount
        && query.state.dataUpdatedAt > best.updatedAt
      )
    ) {
      best = {
        data: placeholder,
        matchCount: items.length,
        updatedAt: query.state.dataUpdatedAt,
      }
    }
  }

  return best?.data
}

export function useTaskLedgerInfinite({
  definitionKey,
  resourceType,
  resourceId,
  status,
  startedAfter,
  orderBy = 'created_at',
  order = 'desc',
  limit = 100,
  enabled = true,
}: TaskLedgerCollectionQuery) {
  const pageActive = usePageActive()
  const resourceIds = normalizeResourceIds(resourceId)
  const statuses = normalizeStatuses(status)
  const startedAfterValue = normalizeStartedAfter(startedAfter)

  return useLazyCollection({
    collectionPrefix: ['taskLedger'] as const,
    queryKey: [
      definitionKey ?? null,
      resourceType ?? null,
      resourceIds ?? null,
      statuses ?? null,
      startedAfterValue ?? null,
      orderBy,
      order,
    ] as const,
    initialCount: limit,
    batchSize: limit,
    enabled: pageActive && enabled && (definitionKey === undefined || definitionKey.length > 0),
    pollIntervalMs: 3000,
    pollWhilePageCountAtMost: 2,
    derivePlaceholderData: (queryClient) => deriveTaskLedgerCollectionPlaceholder(
      queryClient,
      {
        definitionKey,
        resourceType,
        resourceIds,
        statuses,
        startedAfter: startedAfterValue,
        orderBy,
        order,
        initialCount: limit,
      },
    ),
    fetchPage: async ({offset, limit: pageLimit}, signal): Promise<TaskLedgerPageRead> => {
      const params = new URLSearchParams({
        order_by: orderBy,
        order,
        offset: String(offset),
        limit: String(pageLimit),
      })
      if (definitionKey) params.set('definition_key', definitionKey)
      if (resourceType) params.set('resource_type', resourceType)
      for (const id of resourceIds ?? []) params.append('resource_id', String(id))
      for (const item of statuses ?? []) params.append('status', item)
      if (startedAfterValue) params.set('started_after', startedAfterValue)

      const response = await fetch(
        `${(window as any).appConfig.API_URL}/tasks/ledger?${params}`,
        {signal, credentials: 'include'},
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return TaskLedgerPageReadSchema.parse(await response.json())
    },
  })
}
