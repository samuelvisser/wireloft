import { keepPreviousData, useQuery, useQueryClient, QueryClient } from '@tanstack/react-query'

const API_BASE = 'http://localhost:5000/api'

async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export function useMediaProfiles() {
  return useQuery<any[]>({
    queryKey: ['mediaProfiles'],
    queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/media-profiles`, signal),
    placeholderData: keepPreviousData,
  })
}

export function useShows() {
  return useQuery<any[]>({
    queryKey: ['shows'],
    queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/shows`, signal),
    placeholderData: keepPreviousData,
  })
}

export function useShow(id?: string) {
  const qc = useQueryClient()
  return useQuery<any>({
    queryKey: ['show', id],
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
  void qc.prefetchQuery({
    queryKey: ['shows'],
    queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/shows`, signal),
  })
  void qc.prefetchQuery({
    queryKey: ['mediaProfiles'],
    queryFn: ({ signal }) => fetchJSON<any[]>(`${API_BASE}/media-profiles`, signal),
  })
}
