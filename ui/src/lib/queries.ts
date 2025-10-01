import { keepPreviousData, useQuery, useQueryClient, QueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { saveProfilesToStorage, saveShowsToStorage } from './cache'
import {MediaProfileRead} from "../types/schemas/media_profile";

async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal, credentials: 'include' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export function useMediaProfiles() {
  const result = useQuery<any[], Error, MediaProfileRead[], readonly ['mediaProfiles']>({
    queryKey: ['mediaProfiles'] as const,
    queryFn: ({ signal }) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/media-profiles`, signal),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always',
  })
  useEffect(() => {
    if (result.data) saveProfilesToStorage(result.data)
  }, [result.data])
  return result
}

export function useShows() {
  const result = useQuery<any[], Error, any[], readonly ['shows']>({
    queryKey: ['shows'] as const,
    queryFn: ({ signal }) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows`, signal),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always',
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
    queryFn: ({ signal }) => fetchJSON<any>(`${(window as any).appConfig.API_URL}/shows/${id}`, signal),
    placeholderData: keepPreviousData,
    initialData: () => {
      if (!id) return undefined
      const shows = qc.getQueryData<any[]>(['shows'])
      return shows?.find((s) => s.slug === id)
    },
    initialDataUpdatedAt: () => qc.getQueryState(['shows'])?.dataUpdatedAt,
  })
}

export function useEpisodes(showId?: string) {
  return useQuery<any[], Error, any[], readonly ['episodes', string | undefined]>({
    queryKey: ['episodes', showId] as const,
    enabled: !!showId,
    queryFn: ({ signal }) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows/${showId}/episodes`, signal),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always',
  })
}

export function useEpisode(showId?: string, episodeId?: string) {
  return useQuery<any, Error, any, readonly ['episode', string | undefined, string | undefined]>({
    queryKey: ['episode', showId, episodeId] as const,
    enabled: !!showId && !!episodeId,
    queryFn: ({ signal }) => fetchJSON<any>(`${(window as any).appConfig.API_URL}/shows/${showId}/episodes/${episodeId}`, signal),
    placeholderData: keepPreviousData,
  })
}

// Fetch DailyWire show preview by slug for Add Show URL step
export function useDailywireShow(slug?: string, membershipPlan?: string) {
  return useQuery<any, Error, any, readonly ['dwShow', string | undefined, string | undefined]>({
    queryKey: ['dwShow', slug, membershipPlan] as const,
    enabled: !!slug,
    queryFn: async ({ signal }) => {
      const urlBase = (window as any).appConfig.API_URL
      const params = membershipPlan ? `?membership_plan=${encodeURIComponent(membershipPlan)}` : ''
      const url = `${urlBase}/dailywire/shows/${encodeURIComponent(slug!)}` + params
      const r = await fetch(url, { signal, credentials: 'include' })
      if (!r.ok) {
        // Try to surface server-provided error detail and attach status
        try {
          const body = await r.json()
          const detail = typeof body?.detail === 'string' ? body.detail : null
          const err: any = new Error(detail || `HTTP ${r.status}`)
          err.status = r.status
          err.detail = detail
          throw err
        } catch (_) {
          const err: any = new Error(`HTTP ${r.status}`)
          err.status = r.status
          throw err
        }
      }
      return r.json()
    },
    retry: false,
  })
}

// Optional: prefetch core data to warm the cache on app start
export function prefetchCoreData(qc: QueryClient) {
  void qc
    .prefetchQuery({
      queryKey: ['shows'],
      queryFn: ({ signal }) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows`, signal),
    })
    .then(() => {
      const shows = qc.getQueryData<any[]>(['shows'])
      if (shows) saveShowsToStorage(shows)
    })
  void qc
    .prefetchQuery({
      queryKey: ['mediaProfiles'],
      queryFn: ({ signal }) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/media-profiles`, signal),
    })
    .then(() => {
      const profiles = qc.getQueryData<MediaProfileRead[]>(['mediaProfiles'])
      if (profiles) saveProfilesToStorage(profiles)
    })
}
