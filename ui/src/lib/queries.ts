import { keepPreviousData, useQuery, useQueryClient, QueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { saveProfilesToStorage, saveShowsToStorage } from './cache'

const API_BASE = 'http://localhost:5000/api'

async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export function useMediaProfiles() {
  const result = useQuery<any[], Error, any[], readonly ['mediaProfiles']>({
    queryKey: ['mediaProfiles'] as const,
    queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/media-profiles`, signal),
    placeholderData: keepPreviousData,
  })
  useEffect(() => {
    if (result.data) saveProfilesToStorage(result.data)
  }, [result.data])
  return result
}

export function useShows() {
  const result = useQuery<any[], Error, any[], readonly ['shows']>({
    queryKey: ['shows'] as const,
    queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/shows`, signal),
    placeholderData: keepPreviousData,
  })
  useEffect(() => {
    if (result.data) saveShowsToStorage(result.data)
  }, [result.data])
  return result
}

export function useShow(id?: string) {
  const qc = useQueryClient()
  return useQuery<any, Error, any, readonly ['show', string | undefined]>({
    queryKey: ['show', id] as const,
    enabled: !!id,
    queryFn: ({ signal }) => fetchJSON<any>(`${API_BASE}/shows/${id}`, signal),
    placeholderData: keepPreviousData,
    initialData: () => {
      if (!id) return undefined
      const shows = qc.getQueryData<any[]>(['shows'])
      return shows?.find((s) => s.id === id)
    },
    initialDataUpdatedAt: () => qc.getQueryState(['shows'])?.dataUpdatedAt,
  })
}

// Optional: prefetch core data to warm the cache on app start
export function prefetchCoreData(qc: QueryClient) {
  void qc
    .prefetchQuery({
      queryKey: ['shows'],
      queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/shows`, signal),
    })
    .then(() => {
      const shows = qc.getQueryData<any[]>(['shows'])
      if (shows) saveShowsToStorage(shows)
    })
  void qc
    .prefetchQuery({
      queryKey: ['mediaProfiles'],
      queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/media-profiles`, signal),
    })
    .then(() => {
      const profiles = qc.getQueryData<any[]>(['mediaProfiles'])
      if (profiles) saveProfilesToStorage(profiles)
    })
}
