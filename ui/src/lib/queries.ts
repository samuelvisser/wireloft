import {keepPreviousData, QueryClient, useInfiniteQuery, useQuery, useQueryClient} from '@tanstack/react-query'
import {useEffect, useMemo} from 'react'
import {saveProfilesToStorage, saveShowsToStorage} from './cache'
import {useFrontendPuller} from './puller'
import {LocalMediaProfileRead, LocalMediaProfileReadSchema} from "../types/schemas/local_media_profile";
import {PodcastDownloadProfileRead, PodcastDownloadProfileReadSchema} from "../types/schemas/podcast_download_profile";
import {SeriesDownloadProfileRead, SeriesDownloadProfileReadSchema} from "../types/schemas/series_download_profile";
import {DownloadProfileRead, DownloadProfileReadSchema} from "../types/schemas/download_profile_base";
import {DownloadProfileReadView, DownloadProfileReadViewSchema} from "../types/schemas/download_profile_view";
import {StreamProfileRead, StreamProfileReadSchema, StreamProfileReadView, StreamProfileReadViewSchema} from "../types/schemas/stream_profile_base";
import {ShowRead, ShowReadSchema, ShowReadView, ShowReadViewSchema} from "../types/schemas/show";
import {EpisodeRead, EpisodeReadSchema} from "../types/schemas/episode";
import {SeasonRead, SeasonReadSchema} from "../types/schemas/season";
import {RssStreamProfileRead, RssStreamProfileReadSchema} from "../types/schemas/rss_stream_profile";
import {DailywireUserInfoRead, DailywireUserInfoReadSchema} from "../types/schemas/dailywire_user_info";
import {DailywireShowRead} from "../types/schemas/dailywire_show";
import {
    MediaDownloadDomainViewRead,
    MediaDownloadViewRead,
    MediaDownloadViewReadSchema,
} from "../types/schemas/media_download";
import {TaskOperationRead} from "../types/schemas/operation";
import {TaskLedgerPageReadSchema} from "../types/schemas/task";
import {MovieRead, MovieReadSchema} from "../types/schemas/movie";
import {
    DailywireCatalogRead,
    DailywireCatalogReadSchema,
    DailywireCatalogMoviePageReadSchema,
    DailywireCatalogShowPageReadSchema,
    DailywireMovieRead,
    DailywireMovieReadSchema,
} from "../types/schemas/dailywire_catalog";

async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
    const r = await fetch(url, {signal, credentials: 'include'})
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json() as Promise<T>
}

async function fetchParsed<T>(
    url: string,
    schema: {parse(value: unknown): T},
    signal?: AbortSignal,
): Promise<T> {
    return schema.parse(await fetchJSON<unknown>(url, signal))
}

export function useLocalMediaProfiles() {
    const result = useQuery<LocalMediaProfileRead[], Error, LocalMediaProfileRead[], readonly ['localMediaProfiles']>({
        queryKey: ['localMediaProfiles'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/local-media-profiles`,
            LocalMediaProfileReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
    useEffect(() => {
        if (result.data) saveProfilesToStorage(result.data)
    }, [result.data])
    return result
}

export function usePodcastDownloadProfiles() {
    return useQuery<PodcastDownloadProfileRead[], Error, PodcastDownloadProfileRead[], readonly ['podcastDownloadProfiles']>({
        queryKey: ['podcastDownloadProfiles'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/podcast-download-profiles`,
            PodcastDownloadProfileReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useSeriesDownloadProfiles() {
    return useQuery<SeriesDownloadProfileRead[], Error, SeriesDownloadProfileRead[], readonly ['seriesDownloadProfiles']>({
        queryKey: ['seriesDownloadProfiles'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/series-download-profiles`,
            SeriesDownloadProfileReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useDownloadProfilesView() {
    return useQuery<DownloadProfileReadView[], Error, DownloadProfileReadView[], readonly ['downloadProfilesView']>({
        queryKey: ['downloadProfilesView'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/download-profiles/as-view`,
            DownloadProfileReadViewSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useRssStreamProfiles() {
    return useQuery<RssStreamProfileRead[], Error, RssStreamProfileRead[], readonly ['rssStreamProfiles']>({
        queryKey: ['rssStreamProfiles'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/rss-stream-profiles`,
            RssStreamProfileReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useStreamProfilesView() {
    return useQuery<StreamProfileReadView[], Error, StreamProfileReadView[], readonly ['streamProfilesView']>({
        queryKey: ['streamProfilesView'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/stream-profiles/as-view`,
            StreamProfileReadViewSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useShows() {
    const result = useQuery<ShowRead[], Error, ShowRead[], readonly ['shows']>({
        queryKey: ['shows'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/shows`,
            ShowReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
    useEffect(() => {
        if (result.data) saveShowsToStorage(result.data)
    }, [result.data])
    return result
}

export function useShowsView() {
    return useQuery<ShowReadView[], Error, ShowReadView[], readonly ['showsView']>({
        queryKey: ['showsView'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/shows/as-view`,
            ShowReadViewSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useMovies() {
    return useQuery<MovieRead[], Error, MovieRead[], readonly ['movies']>({
        queryKey: ['movies'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/movies`,
            MovieReadSchema.array(),
            signal,
        ),
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

const DAILYWIRE_CATALOG_PAGE_SIZE = 24

export function useDailywireShowCatalog(search: string, grouping: 'host' | 'alphabetical', enabled = true) {
    return useInfiniteQuery({
        queryKey: ['dailywireCatalog', 'shows', search, grouping] as const,
        enabled,
        initialPageParam: 0,
        queryFn: async ({pageParam, signal}) => {
            const params = new URLSearchParams({
                offset: String(pageParam),
                limit: String(DAILYWIRE_CATALOG_PAGE_SIZE),
                grouping,
            })
            if (search) params.set('search', search)
            const value = await fetchJSON<any>(
                `${(window as any).appConfig.API_URL}/dailywire/catalog/shows?${params}`,
                signal,
            )
            return DailywireCatalogShowPageReadSchema.parse(value)
        },
        getNextPageParam: (lastPage) => lastPage.hasMore
            ? lastPage.offset + lastPage.items.length
            : undefined,
        staleTime: 5 * 60 * 1000,
        gcTime: 30 * 60 * 1000,
        refetchOnMount: false,
    })
}

export function useDailywireMovieCatalog(search: string, enabled = true) {
    return useInfiniteQuery({
        queryKey: ['dailywireCatalog', 'movies', search] as const,
        enabled,
        initialPageParam: 0,
        queryFn: async ({pageParam, signal}) => {
            const params = new URLSearchParams({
                offset: String(pageParam),
                limit: String(DAILYWIRE_CATALOG_PAGE_SIZE),
            })
            if (search) params.set('search', search)
            const value = await fetchJSON<any>(
                `${(window as any).appConfig.API_URL}/dailywire/catalog/movies?${params}`,
                signal,
            )
            return DailywireCatalogMoviePageReadSchema.parse(value)
        },
        getNextPageParam: (lastPage) => lastPage.hasMore
            ? lastPage.offset + lastPage.items.length
            : undefined,
        staleTime: 5 * 60 * 1000,
        gcTime: 30 * 60 * 1000,
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
    return useQuery<ShowRead, Error, ShowRead, readonly ['show', string | undefined]>({
        queryKey: ['show', id] as const,
        enabled: !!id,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/shows/${id}`,
            ShowReadSchema,
            signal,
        ),
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
    return useQuery<EpisodeRead[], Error, EpisodeRead[], readonly ['episodes', string | undefined, number | undefined]>({
        queryKey: ['episodes', showSlug, opts?.limit] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => {
            const base = (window as any).appConfig.API_URL
            const params = opts?.limit ? `?limit=${opts.limit}` : ''
            return fetchParsed(
                `${base}/episodes/by-show-slug/${showSlug}${params}`,
                EpisodeReadSchema.array(),
                signal,
            )
        },
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useEpisode(episodeId?: string) {
    return useQuery<EpisodeRead, Error, EpisodeRead, readonly ['episode', string | undefined]>({
        queryKey: ['episode', episodeId] as const,
        enabled: !!episodeId,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/episodes/${episodeId}`,
            EpisodeReadSchema,
            signal,
        ),
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
    return useQuery<SeasonRead[], Error, SeasonRead[], readonly ['seasons', string | undefined]>({
        queryKey: ['seasons', showSlug] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/shows/${showSlug}/seasons`,
            SeasonReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useDownloadProfilesByShowSlug(showSlug?: string) {
    return useQuery<DownloadProfileRead[], Error, DownloadProfileRead[], readonly ['downloadProfilesByShowSlug', string | undefined]>({
        queryKey: ['downloadProfilesByShowSlug', showSlug] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/download-profiles/by-show-slug/${showSlug}`,
            DownloadProfileReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useStreamProfilesByShowSlug(showSlug?: string) {
    return useQuery<StreamProfileRead[], Error, StreamProfileRead[], readonly ['streamProfilesByShowSlug', string | undefined]>({
        queryKey: ['streamProfilesByShowSlug', showSlug] as const,
        enabled: !!showSlug,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/stream-profiles/by-show-slug/${showSlug}`,
            StreamProfileReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

const ACTIVE_OPERATION_STATUSES = new Set(['QUEUED', 'RUNNING'])

function contextString(operation: TaskOperationRead, key: string): string | null {
    const value = operation.context?.[key]
    return typeof value === 'string' ? value : null
}

function contextNumber(operation: TaskOperationRead, key: string): number | null {
    const value = operation.context?.[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function contextBoolean(operation: TaskOperationRead, key: string): boolean | null {
    const value = operation.context?.[key]
    return typeof value === 'boolean' ? value : null
}

function operationDate(value: string | null | undefined): Date | null {
    if (!value) return null
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? null : parsed
}

function operationForDownload(
    operations: TaskOperationRead[],
    mediaDownloadId: number,
): TaskOperationRead | undefined {
    return operations.find((operation) => (
        operation.kind === 'media.download'
        && operation.resourceType === 'media_download'
        && operation.resourceId === mediaDownloadId
    ))
}

function presentationStatus(
    download: MediaDownloadDomainViewRead,
    operation?: TaskOperationRead,
): string {
    if (operation?.status === 'QUEUED') return 'pending'
    if (operation?.status === 'RUNNING') return 'downloading'
    if (operation?.status === 'FAILED' || operation?.status === 'PARTIAL') return 'error'
    if (operation?.status === 'CANCELED') return 'cancelled'
    if (operation?.status === 'SUCCEEDED') {
        return contextBoolean(operation, 'is_redownload') ? 'redownloaded' : 'downloaded'
    }

    if (download.artifactStatus === 'available') {
        return download.latestTaskIsRedownload ? 'redownloaded' : 'downloaded'
    }
    if (download.artifactStatus === 'missing') return 'missing'
    if (download.artifactStatus === 'corrupted') return 'corrupted'
    if (download.automaticRetrySuppressed) return 'cancelled'
    if (download.latestTaskStatus === 'CANCELED') return 'cancelled'
    if (download.latestTaskStatus === 'FAILED') return 'error'
    if (download.latestTaskStatus === 'RUNNING') return 'downloading'
    return 'pending'
}

function presentDownload(
    download: MediaDownloadDomainViewRead,
    operation?: TaskOperationRead,
): MediaDownloadViewRead {
    const status = presentationStatus(download, operation)
    const operationError = operation?.status === 'FAILED'
        ? (operation.error || operation.message || null)
        : null
    return {
        ...download,
        downloadStatus: status,
        progress: operation && ACTIVE_OPERATION_STATUSES.has(operation.status)
            ? Math.max(0, Math.min(100, operation.progress ?? 0))
            : status === 'downloaded' || status === 'redownloaded'
                ? 100
                : 0,
        errorMessage: operationError || download.artifactError || download.latestTaskError,
        startedAt: operationDate(operation?.startedAt) || download.latestTaskStartedAt,
        finishedAt: operationDate(operation?.finishedAt) || download.downloadedAt || download.latestTaskFinishedAt,
        isRedownloadAttempt: operation
            ? contextBoolean(operation, 'is_redownload')
            : download.latestTaskIsRedownload,
    }
}

function syntheticDownload(operation: TaskOperationRead): MediaDownloadDomainViewRead | null {
    if (
        operation.kind !== 'media.download'
        || operation.resourceType !== 'media_download'
        || operation.resourceId == null
        || !ACTIVE_OPERATION_STATUSES.has(operation.status)
    ) {
        return null
    }

    const mediaItemId = contextNumber(operation, 'media_item_id')
    const localMediaProfileId = contextNumber(operation, 'local_media_profile_id')
    if (mediaItemId == null || localMediaProfileId == null) return null

    const createdAt = operationDate(operation.createdAt) || new Date()
    return {
        id: operation.resourceId,
        type: contextString(operation, 'media_type') || 'episode',
        mediaItemId,
        localMediaProfileId,
        filePath: contextString(operation, 'file_path') || '',
        artifactStatus: 'absent',
        artifactError: null,
        automaticRetrySuppressed: false,
        downloadedBytes: null,
        formatDownloaded: null,
        downloadedAt: null,
        createdAt,
        updatedAt: operationDate(operation.updatedAt) || createdAt,
        mediaSlug: contextString(operation, 'media_slug'),
        mediaTitle: contextString(operation, 'media_title'),
        episodeSlug: contextString(operation, 'episode_slug'),
        episodeTitle: contextString(operation, 'episode_title'),
        episodeIdentifier: contextString(operation, 'episode_identifier'),
        showSlug: contextString(operation, 'show_slug'),
        showTitle: contextString(operation, 'show_title'),
        movieSlug: contextString(operation, 'movie_slug'),
        movieTitle: contextString(operation, 'movie_title'),
        movieExtraType: contextString(operation, 'movie_extra_type'),
        localMediaProfileName: contextString(operation, 'local_media_profile_name'),
        preferredFormat: contextString(operation, 'preferred_format'),
        downloadedPublishStatus: null,
        latestTaskStatus: null,
        latestTaskError: null,
        latestTaskIsRedownload: null,
        latestTaskStartedAt: null,
        latestTaskFinishedAt: null,
    }
}

function useMediaDownloadPresentation() {
    const domainQuery = useQuery<unknown[], Error, MediaDownloadDomainViewRead[], readonly ['mediaDownloadsView']>({
        queryKey: ['mediaDownloadsView'] as const,
        queryFn: async ({signal}) => {
            const value = await fetchJSON<unknown[]>(
                `${(window as any).appConfig.API_URL}/media-downloads/as-view`,
                signal,
            )
            return MediaDownloadViewReadSchema.array().parse(value)
        },
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
    const {data: pullData} = useFrontendPuller()
    const operations = pullData?.operations ?? []

    const data = useMemo(() => {
        if (domainQuery.data === undefined && operations.length === 0) return undefined

        const downloads = new Map<number, MediaDownloadDomainViewRead>()
        for (const download of domainQuery.data ?? []) downloads.set(download.id, download)
        for (const operation of operations) {
            if (operation.kind !== 'media.download' || operation.resourceId == null) continue
            if (!downloads.has(operation.resourceId)) {
                const synthetic = syntheticDownload(operation)
                if (synthetic) downloads.set(synthetic.id, synthetic)
            }
        }

        return [...downloads.values()]
            .map((download) => presentDownload(
                download,
                operationForDownload(operations, download.id),
            ))
            .sort((left, right) => right.id - left.id)
    }, [domainQuery.data, operations])

    return {...domainQuery, data}
}

export function useEpisodeDownloads(episodeSlug?: string) {
    const query = useMediaDownloadPresentation()
    const data = useMemo(
        () => query.data?.filter((download) => download.episodeSlug === episodeSlug),
        [episodeSlug, query.data],
    )
    return {...query, data}
}

export function useMovieDownloads(movieSlug?: string) {
    const query = useMediaDownloadPresentation()
    const data = useMemo(
        () => query.data?.filter((download) => download.movieSlug === movieSlug),
        [movieSlug, query.data],
    )
    return {...query, data}
}

export function useMediaDownloadsView() {
    return useMediaDownloadPresentation()
}

type TaskLedgerQuery = {
    definitionKey: string
    resourceType?: string
    resourceId?: number
    orderBy?: 'started_at' | 'finished_at' | 'created_at'
    order?: 'asc' | 'desc'
    limit?: number
    enabled?: boolean
}

export function useTaskLedger({
    definitionKey,
    resourceType,
    resourceId,
    orderBy = 'started_at',
    order = 'desc',
    limit = 50,
    enabled = true,
}: TaskLedgerQuery) {
    return useInfiniteQuery({
        queryKey: ['taskLedger', definitionKey, resourceType, resourceId, orderBy, order, limit] as const,
        enabled: enabled && definitionKey.length > 0,
        initialPageParam: 0,
        queryFn: async ({pageParam, signal}) => {
            const params = new URLSearchParams({
                definition_key: definitionKey,
                order_by: orderBy,
                order,
                offset: String(pageParam),
                limit: String(limit),
            })
            if (resourceType) params.set('resource_type', resourceType)
            if (resourceId !== undefined) params.set('resource_id', String(resourceId))
            const value = await fetchJSON<unknown>(
                `${(window as any).appConfig.API_URL}/tasks/ledger?${params}`,
                signal,
            )
            return TaskLedgerPageReadSchema.parse(value)
        },
        getNextPageParam: (lastPage) => lastPage.hasMore
            ? lastPage.offset + lastPage.items.length
            : undefined,
        refetchOnMount: 'always',
    })
}

// Prefetch core data to warm the cache on app start
export function prefetchCoreData(qc: QueryClient) {
    void qc
        .prefetchQuery({
            queryKey: ['shows'],
            queryFn: ({signal}) => fetchParsed(
                `${(window as any).appConfig.API_URL}/shows`,
                ShowReadSchema.array(),
                signal,
            ),
        })
        .then(() => {
            const shows = qc.getQueryData<ShowRead[]>(['shows'])
            if (shows) saveShowsToStorage(shows)
        })
    void qc.prefetchQuery({
        queryKey: ['movies'],
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/movies`,
            MovieReadSchema.array(),
            signal,
        ),
    })
    void qc
        .prefetchQuery({
            queryKey: ['localMediaProfiles'],
            queryFn: ({signal}) => fetchParsed(
                `${(window as any).appConfig.API_URL}/local-media-profiles`,
                LocalMediaProfileReadSchema.array(),
                signal,
            ),
        })
        .then(() => {
            const profiles = qc.getQueryData<LocalMediaProfileRead[]>(['localMediaProfiles'])
            if (profiles) saveProfilesToStorage(profiles)
        })
    void qc.prefetchQuery({
        queryKey: ['podcastDownloadProfiles'],
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/podcast-download-profiles`,
            PodcastDownloadProfileReadSchema.array(),
            signal,
        ),
    })
    void qc.prefetchQuery({
        queryKey: ['seriesDownloadProfiles'],
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/series-download-profiles`,
            SeriesDownloadProfileReadSchema.array(),
            signal,
        ),
    })
    void qc.prefetchQuery({
        queryKey: ['downloadProfilesView'],
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/download-profiles/as-view`,
            DownloadProfileReadViewSchema.array(),
            signal,
        ),
    })
    void qc.prefetchQuery({
        queryKey: ['rssStreamProfiles'],
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/rss-stream-profiles`,
            RssStreamProfileReadSchema.array(),
            signal,
        ),
    })
    void qc.prefetchQuery({
        queryKey: ['streamProfilesView'],
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/stream-profiles/as-view`,
            StreamProfileReadViewSchema.array(),
            signal,
        ),
    })
}
