import {keepPreviousData, queryOptions, type QueryClient} from '@tanstack/react-query'

import {EpisodeReadViewSchema} from '../types/schemas/episode'
import {SeasonReadSchema} from '../types/schemas/season'
import {ShowRead, ShowReadSchema} from '../types/schemas/show'

function apiBase() {
  return ((window as any).appConfig?.API_URL || '/api').replace(/\/+$/, '')
}

async function fetchParsed<T>(
  url: string,
  schema: {parse(value: unknown): T},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {signal, credentials: 'include'})
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return schema.parse(await response.json())
}

export function showsQueryOptions() {
  return queryOptions({
    queryKey: ['shows'] as const,
    queryFn: ({signal}) => fetchParsed(
      `${apiBase()}/shows`,
      ShowReadSchema.array(),
      signal,
    ),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always' as const,
  })
}

export function showQueryOptions(id: string | undefined, queryClient: QueryClient) {
  return queryOptions({
    queryKey: ['show', id] as const,
    queryFn: ({signal}) => fetchParsed(
      `${apiBase()}/shows/${encodeURIComponent(id!)}`,
      ShowReadSchema,
      signal,
    ),
    placeholderData: keepPreviousData,
    initialData: () => {
      if (!id) return undefined
      const shows = queryClient.getQueryData<ShowRead[]>(showsQueryOptions().queryKey)
      return shows?.find((show) => show.slug === id)
    },
    initialDataUpdatedAt: () => queryClient.getQueryState(showsQueryOptions().queryKey)?.dataUpdatedAt,
  })
}

export function episodesQueryOptions(showSlug: string | undefined, limit?: number) {
  return queryOptions({
    queryKey: ['episodes', showSlug, limit] as const,
    queryFn: ({signal}) => {
      const params = limit ? `?limit=${limit}` : ''
      return fetchParsed(
        `${apiBase()}/episodes/as-view/by-show-slug/${encodeURIComponent(showSlug!)}${params}`,
        EpisodeReadViewSchema.array(),
        signal,
      )
    },
    placeholderData: keepPreviousData,
    refetchOnMount: 'always' as const,
  })
}

export function seasonsQueryOptions(showSlug: string | undefined) {
  return queryOptions({
    queryKey: ['seasons', showSlug] as const,
    queryFn: ({signal}) => fetchParsed(
      `${apiBase()}/shows/${encodeURIComponent(showSlug!)}/seasons`,
      SeasonReadSchema.array(),
      signal,
    ),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always' as const,
  })
}
