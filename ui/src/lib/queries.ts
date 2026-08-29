import {keepPreviousData, QueryClient, useQuery, useQueryClient} from '@tanstack/react-query'
import {useEffect} from 'react'
import {saveProfilesToStorage, saveShowsToStorage} from './cache'
import {LocalMediaProfileRead} from "../types/schemas/local_media_profile";
import {PodcastDownloadProfileRead} from "../types/schemas/podcast_download_profile";
import {SeriesDownloadProfileRead} from "../types/schemas/series_download_profile";
import {DownloadProfileRead} from "../types/schemas/download_profile_base";
import {DownloadProfileReadView} from "../types/schemas/download_profile_view";
import {StreamProfileRead, StreamProfileReadView} from "../types/schemas/stream_profile_base";
import {ShowRead, ShowReadView} from "../types/schemas/show";
import {EpisodeRead} from "../types/schemas/episode";
import {SeasonRead} from "../types/schemas/season";
import {RssStreamProfileRead} from "../types/schemas/rss_stream_profile";
import {DailywireUserInfoRead, DailywireUserInfoReadSchema} from "../types/schemas/dailywire_user_info";
import {DailywireShowRead} from "../types/schemas/dailywire_show";
import {TaskRunRead, TaskRunReadSchema} from "../types/schemas/task";
import {MediaDownloadAttemptRead, MediaDownloadViewRead} from "../types/schemas/media_download";
import {ACTIVE_DOWNLOAD_STATUSES} from "../types/media_download";
import {MovieRead} from "../types/schemas/movie";
import {
    DailywireCatalogRead,
    DailywireCatalogReadSchema,
    DailywireMovieRead,
    DailywireMovieReadSchema,
} from "../types/schemas/dailywire_catalog";

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

export function useShowsView() {
    return useQuery<any[], Error, ShowReadView[], readonly ['showsView']>({
        queryKey: ['showsView'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/shows/as-view`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useMovies() {
    return useQuery<any[], Error, MovieRead[], readonly ['movies']>({
        queryKey: ['movies'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/movies`, signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useDailywireCatalog() {
    return useQuery<any, Error, DailywireCatalogRead, readonly ['dailywireCatalog']>({
        queryKey: ['dailywireCatalog'] as const,
        queryFn: async ({signal}) => {
            const value = await fetchJSON<any>(`${(window as any).appConfig.API_URL}/dailywire/catalog`, signal)
            return DailywireCatalogReadSchema.parse(value)
        },
        staleTime: 5 * 60 * 1000,
        refetchOnMount: false,
    })
}

export function useDailywireMovie(slug?: string) {
    return useQuery<any, Error, DailywireMovieRead, readonly ['dailywireMovie', string | undefined]>({
        queryKey: ['dailywireMovie', slug] as const,
        enabled: !!slug,
        queryFn: async ({signal}) => {
            const value = await fetchJSON<any>(
                `${(window as any).appConfig.API_URL}/dailywire/movies/${encodeURIComponent(slug!)}`,
                signal,
            )
            return DailywireMovieReadSchema.parse(value)
        },
        staleTime: 5 * 60 * 1000,
    })
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

export function useEpisodes(showSlug?: string, opts?: { limit?: number }) {
    return useQuery<any[], Error, EpisodeRead[], readonly ['episodes', string | undefined, number | undefined]>({
        queryKey: ['episodes', showSlug, opts?.limit] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => {
            const base = (window as any).appConfig.API_URL
            const params = opts?.limit ? `?limit=${opts.limit}` : ''
            return fetchJSON<any[]>(`${base}/episodes/by-show-slug/${showSlug}${params}`, signal)
        },
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useEpisode(episodeId?: string) {
    return useQuery<any, Error, EpisodeRead, readonly ['episode', string | undefined]>({
        queryKey: ['episode', episodeId] as const,
        enabled: !!episodeId,
        queryFn: ({signal}) => fetchJSON<any>(`${(window as any).appConfig.API_URL}/episodes/${episodeId}`, signal),
        placeholderData: keepPreviousData,
    })
}

// Fetch DailyWire show preview by slug for Add Show URL step
export function useDailywireShow(slug?: string, membershipPlan?: string) {
    return useQuery<any, Error, DailywireShowRead, readonly ['dwShow', string | undefined, string | undefined]>({
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

export function useDailywireUserInfo() {
    return useQuery<any, any & { status?: number }, DailywireUserInfoRead, readonly ['dwUserInfo']>({
        queryKey: ['dwUserInfo'] as const,
        queryFn: async ({signal}) => {
            const base = (window as any).appConfig?.API_URL?.replace(/\/+$/, '')
            const r = await fetch(`${base}/dailywire/user-info`, { signal, credentials: 'include' })
            if (!r.ok) {
                const err: any = new Error(`HTTP ${r.status}`)
                err.status = r.status
                try {
                    const body = await r.json()
                    if (typeof body?.detail === 'string') err.detail = body.detail
                } catch {}
                throw err
            }
            const j = await r.json()
            return DailywireUserInfoReadSchema.parse(j)
        },
        retry: false,
        refetchOnMount: 'always',
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

function hasActiveDownloads(rows: unknown): boolean {
    return Array.isArray(rows) && rows.some((r) => ACTIVE_DOWNLOAD_STATUSES.has(String(r?.downloadStatus)))
}

export function useEpisodeDownloads(episodeSlug?: string) {
    return useQuery<any[], Error, MediaDownloadViewRead[], readonly ['episodeDownloads', string | undefined]>({
        queryKey: ['episodeDownloads', episodeSlug] as const,
        enabled: !!episodeSlug,
        queryFn: ({signal}) => {
            const base = (window as any).appConfig.API_URL
            return fetchJSON<any[]>(`${base}/media-downloads/as-view?episode_slug=${encodeURIComponent(episodeSlug!)}`, signal)
        },
        // Poll while a download is running; starting one invalidates this key
        refetchInterval: (q) => (hasActiveDownloads(q.state.data) ? 1500 : false),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useMovieDownloads(movieSlug?: string) {
    return useQuery<any[], Error, MediaDownloadViewRead[], readonly ['movieDownloads', string | undefined]>({
        queryKey: ['movieDownloads', movieSlug] as const,
        enabled: !!movieSlug,
        queryFn: ({signal}) => fetchJSON<any[]>(
            `${(window as any).appConfig.API_URL}/media-downloads/as-view?movie_slug=${encodeURIComponent(movieSlug!)}`,
            signal,
        ),
        refetchInterval: (query) => (hasActiveDownloads(query.state.data) ? 1500 : false),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useMediaDownloadsView() {
    return useQuery<any[], Error, MediaDownloadViewRead[], readonly ['mediaDownloadsView']>({
        queryKey: ['mediaDownloadsView'] as const,
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/media-downloads/as-view`, signal),
        // Poll fast while anything is downloading; keep a slow heartbeat otherwise
        // so downloads started elsewhere show up while the page stays open
        refetchInterval: (q) => (hasActiveDownloads(q.state.data) ? 1500 : 8000),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useMediaDownloadAttempts(mediaDownloadId?: number) {
    return useQuery<any[], Error, MediaDownloadAttemptRead[], readonly ['mediaDownloadAttempts', number | undefined]>({
        queryKey: ['mediaDownloadAttempts', mediaDownloadId] as const,
        enabled: mediaDownloadId != null,
        queryFn: ({signal}) =>
            fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/media-downloads/${mediaDownloadId}/attempts`, signal),
        // A light poll so a ledger entry from a redownload finishing while the
        // log dialog is open shows up without the user having to reopen it.
        refetchInterval: 2000,
        refetchOnMount: 'always',
    })
}

// Prefetch core data to warm the cache on app start
export function useShowIndexingRun(showId?: number) {
    return useQuery<any, Error, TaskRunRead | null, readonly ['showIndexingRun', number | undefined]>({
        queryKey: ['showIndexingRun', showId] as const,
        enabled: !!showId,
        queryFn: async ({signal}) => {
            const base: string = (window as any).appConfig.API_URL
            const url = `${base}/tasks/runs?resource_type=show&resource_id=${showId}&definition_key=fetch_new_episodes&status=RUNNING`
            const data: any[] = await fetchJSON<any[]>(url, signal)

            if(Array.isArray(data) && data.length > 0) {
                return TaskRunReadSchema.parse(data[0])
            }
            return null
        },
        // Poll periodically while enabled (when an active run exists)
        refetchInterval: (q) => {
            const r = q.state.data as TaskRunRead[] | null
            return r ? 1500 : false
        },
        placeholderData: null,
        refetchOnMount: 'always',
    })
}

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
    void qc.prefetchQuery({
        queryKey: ['movies'],
        queryFn: ({signal}) => fetchJSON<any[]>(`${(window as any).appConfig.API_URL}/movies`, signal),
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
