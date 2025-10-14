import {keepPreviousData, useQuery, useQueryClient, QueryClient} from '@tanstack/react-query'
import {useEffect} from 'react'
import {saveProfilesToStorage, saveShowsToStorage} from './cache'
import {LocalMediaProfileRead} from "../types/schemas/local_media_profile";
import {PodcastDownloadProfileRead} from "../types/schemas/podcast_download_profile";
import {SeriesDownloadProfileRead} from "../types/schemas/series_download_profile";
import {DownloadProfileRead, DownloadProfileReadView} from "../types/schemas/download_profile_base";
import {StreamProfileRead, StreamProfileReadView} from "../types/schemas/stream_profile_base";
import {ShowRead} from "../types/schemas/show";
import {EpisodeRead} from "../types/schemas/episode";
import {SeasonRead} from "../types/schemas/season";
import {RssStreamProfileRead} from "../types/schemas/rss_stream_profile";

async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
    const r = await fetch(url, {signal, credentials: 'include'})
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json() as Promise<T>
}

export function useLocalMediaProfiles() {
    const result = useQuery<any[], Error, LocalMediaProfileRead[], readonly ['localMediaProfiles']>({
        queryKey: ['localMediaProfiles'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/local-media-profiles`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
    useEffect(() => {
        if (result.data) saveProfilesToStorage(result.data)
    }, [result.data])
    return result
}

export function usePodcastDownloadProfiles() {
    return useQuery<any[], Error, PodcastDownloadProfileRead[], readonly ['podcastDownloadProfiles']>({
        queryKey: ['podcastDownloadProfiles'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/podcast-download-profiles`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useSeriesDownloadProfiles() {
    return useQuery<any[], Error, SeriesDownloadProfileRead[], readonly ['seriesDownloadProfiles']>({
        queryKey: ['seriesDownloadProfiles'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/series-download-profiles`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useDownloadProfilesView() {
    return useQuery<any[], Error, DownloadProfileReadView[], readonly ['downloadProfilesView']>({
        queryKey: ['downloadProfilesView'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/download-profiles/as-view`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useRssStreamProfiles() {
    return useQuery<any[], Error, RssStreamProfileRead[], readonly ['rssStreamProfiles']>({
        queryKey: ['rssStreamProfiles'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/rss-stream-profiles`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useStreamProfilesView() {
    return useQuery<any[], Error, StreamProfileReadView[], readonly ['streamProfilesView']>({
        queryKey: ['streamProfilesView'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/stream-profiles/as-view`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useShows() {
    const result = useQuery<any[], Error, ShowRead[], readonly ['shows']>({
        queryKey: ['shows'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows`, signal),
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
    return useQuery<any, Error, ShowRead, readonly ['show', string | undefined]>({
        queryKey: ['show', id] as const,
        enabled: !!id,
        queryFn: ({signal}) => fetchJSON<any>(`${(window as any).appConfig.API_URL}/shows/${id}`, signal),
        placeholderData: keepPreviousData,
        initialData: () => {
            if (!id) return undefined
            const shows = qc.getQueryData<ShowRead[]>(['shows'])
            return shows?.find((s) => s.slug === id)
        },
        initialDataUpdatedAt: () => qc.getQueryState(['shows'])?.dataUpdatedAt,
    })
}

export function useEpisodes(showId?: string) {
    return useQuery<any[], Error, EpisodeRead[], readonly ['episodes', string | undefined]>({
        queryKey: ['episodes', showId] as const,
        enabled: !!showId,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows/${showId}/episodes`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useEpisode(showId?: string, episodeId?: string) {
    return useQuery<any, Error, EpisodeRead, readonly ['episode', string | undefined, string | undefined]>({
        queryKey: ['episode', showId, episodeId] as const,
        enabled: !!showId && !!episodeId,
        queryFn: ({signal}) => fetchJSON<any>(`${(window as any).appConfig.API_URL}/shows/${showId}/episodes/${episodeId}`, signal),
        placeholderData: keepPreviousData,
    })
}

// Fetch DailyWire show preview by slug for Add Show URL step
export function useDailywireShow(slug?: string, membershipPlan?: string) {
    return useQuery<any, Error, any, readonly ['dwShow', string | undefined, string | undefined]>({
        queryKey: ['dwShow', slug, membershipPlan] as const,
        enabled: !!slug,
        queryFn: async ({signal}) => {
            const urlBase = (window as any).appConfig.API_URL
            const params = membershipPlan ? `?membership_plan=${encodeURIComponent(membershipPlan)}` : ''
            const url = `${urlBase}/dailywire/shows/${encodeURIComponent(slug!)}` + params
            const r = await fetch(url, {signal, credentials: 'include'})
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

export function useShowSeasons(showSlug?: string) {
    return useQuery<any[], Error, SeasonRead[], readonly ['seasons', string | undefined]>({
        queryKey: ['seasons', showSlug] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows/${showSlug}/seasons`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useDownloadProfilesByShowSlug(showSlug?: string) {
    return useQuery<any[], Error, DownloadProfileRead[], readonly ['downloadProfilesByShowSlug', string | undefined]>({
        queryKey: ['downloadProfilesByShowSlug', showSlug] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/download-profiles/by-show-slug/${showSlug}`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useStreamProfilesByShowSlug(showSlug?: string) {
    return useQuery<any[], Error, StreamProfileRead[], readonly ['streamProfilesByShowSlug', string | undefined]>({
        queryKey: ['streamProfilesByShowSlug', showSlug] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/stream-profiles/by-show-slug/${showSlug}`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

// Prefetch core data to warm the cache on app start
export function prefetchCoreData(qc: QueryClient) {
    void qc
        .prefetchQuery({
            queryKey: ['shows'],
            queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows`, signal),
        })
        .then(() => {
            const shows = qc.getQueryData<any[]>(['shows'])
            if (shows) saveShowsToStorage(shows)
        })
    void qc
        .prefetchQuery({
            queryKey: ['localMediaProfiles'],
            queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/local-media-profiles`, signal),
        })
        .then(() => {
            const profiles = qc.getQueryData<LocalMediaProfileRead[]>(['localMediaProfiles'])
            if (profiles) saveProfilesToStorage(profiles)
        })
    void qc.prefetchQuery({
        queryKey: ['podcastDownloadProfiles'],
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/podcast-download-profiles`, signal),
    })
    void qc.prefetchQuery({
        queryKey: ['seriesDownloadProfiles'],
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/series-download-profiles`, signal),
    })
    void qc.prefetchQuery({
        queryKey: ['downloadProfilesView'],
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/download-profiles/as-view`, signal),
    })
    void qc.prefetchQuery({
        queryKey: ['rssStreamProfiles'],
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/rss-stream-profiles`, signal),
    })
    void qc.prefetchQuery({
        queryKey: ['streamProfilesView'],
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/stream-profiles/as-view`, signal),
    })
}