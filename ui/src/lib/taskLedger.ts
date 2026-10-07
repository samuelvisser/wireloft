import {keepPreviousData, useQuery} from '@tanstack/react-query'
import {useLazyCollection} from './lazyCollection'
import {TaskLedgerPageReadSchema, type TaskLedgerPageRead} from '../types/schemas/task'
import {usePageActive} from './pageActivity'

export type TaskLedgerPageQuery = {
  definitionKey?: string
  resourceType?: string
  resourceId?: number | readonly number[]
  status?: readonly string[]
  startedAfter?: Date | string
  orderBy?: 'started_at' | 'finished_at' | 'created_at'
  order?: 'asc' | 'desc'
  offset?: number
  limit?: number
  enabled?: boolean
}

function normalizeResourceIds(value: TaskLedgerPageQuery['resourceId']): number[] | undefined {
  if (value === undefined) return undefined
  const values = typeof value === 'number' ? [value] : [...value]
  return [...new Set(values)].sort((left, right) => left - right)
}

function normalizeStatuses(value: TaskLedgerPageQuery['status']): string[] | undefined {
  if (value === undefined) return undefined
  return [...new Set(value)].sort()
}

function normalizeStartedAfter(value: TaskLedgerPageQuery['startedAfter']): string | undefined {
  if (value === undefined) return undefined
  return value instanceof Date ? value.toISOString() : value
}

export function useTaskLedgerPage({
  definitionKey,
  resourceType,
  resourceId,
  status,
  startedAfter,
  orderBy = 'started_at',
  order = 'desc',
  offset = 0,
  limit = 50,
  enabled = true,
}: TaskLedgerPageQuery) {
  const resourceIds = normalizeResourceIds(resourceId)
  const statuses = normalizeStatuses(status)
  const startedAfterValue = normalizeStartedAfter(startedAfter)

  return useQuery({
    queryKey: [
      'taskLedger',
      definitionKey ?? null,
      resourceType,
      resourceIds,
      statuses,
      startedAfterValue,
      orderBy,
      order,
      limit,
      'page',
      offset,
    ] as const,
    enabled: enabled && (definitionKey === undefined || definitionKey.length > 0),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always',
    queryFn: async ({signal}): Promise<TaskLedgerPageRead> => {
      const params = new URLSearchParams({
        order_by: orderBy,
        order,
        offset: String(offset),
        limit: String(limit),
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
}: Omit<TaskLedgerPageQuery, 'offset'>) {
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
