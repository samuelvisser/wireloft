import {presentDownloadProgress} from './downloadProgress'
import {
    type InfiniteData,
    keepPreviousData,
    QueryClient,
    useInfiniteQuery,
    useQuery,
    useQueryClient,
} from '@tanstack/react-query'
import {useEffect, useMemo, useRef} from 'react'
import {saveEpisodePreviewToStorage, saveProfilesToStorage, saveShowsToStorage} from './cache'
import {
    type LazyCollectionPage,
    type LazyCollectionPageRequest,
    contiguousLazyCollectionItems,
    lazyCollectionQueryKey,
    updateLazyCollectionEntities,
    useLazyCollection,
} from './lazyCollection'
import {useFrontendPuller} from './puller'
import {downloadStatusesForApi} from './downloadStatusFilters'
import {
    episodeQueryKeys,
    fetchEpisodePage,
    seasonsQueryOptions,
    SHOW_EPISODE_PREVIEW_SIZE,
    showQueryOptions,
    showsQueryOptions,
} from './showQueryOptions'
import {
    LocalMediaProfileRead,
    LocalMediaProfileReadSchema,
    LocalMediaProfileViewRead,
    LocalMediaProfileViewReadSchema,
} from "../types/schemas/local_media_profile";
import {PodcastDownloadProfileRead, PodcastDownloadProfileReadSchema} from "../types/schemas/podcast_download_profile";
import {SeriesDownloadProfileRead, SeriesDownloadProfileReadSchema} from "../types/schemas/series_download_profile";
import {DownloadProfileRead, DownloadProfileReadSchema} from "../types/schemas/download_profile_base";
import {DownloadProfileReadView, DownloadProfileReadViewSchema} from "../types/schemas/download_profile_view";
import {StreamProfileRead, StreamProfileReadSchema, StreamProfileReadView, StreamProfileReadViewSchema} from "../types/schemas/stream_profile_base";
import {ShowRead, ShowReadView, ShowReadViewSchema} from "../types/schemas/show";
import {
    EpisodeIndexedActivityRead,
    EpisodeIndexedActivityReadSchema,
    EpisodeRead,
    EpisodeReadSchema,
    EpisodeReadView,
    EpisodeReadViewPage,
} from "../types/schemas/episode";
import {RssStreamProfileRead, RssStreamProfileReadSchema} from "../types/schemas/rss_stream_profile";
import {DailywireUserInfoRead, DailywireUserInfoReadSchema} from "../types/schemas/dailywire_user_info";
import {DailywireShowRead} from "../types/schemas/dailywire_show";
import {
    MediaDownloadDomainViewRead,
    MediaDownloadPageReadSchema,
    MediaDownloadViewRead,
    MediaDownloadViewReadSchema,
} from "../types/schemas/media_download";
import {TaskOperationRead} from "../types/schemas/operation";
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
        refetchOnMount: 'always',
    })
    useEffect(() => {
        if (result.data) saveProfilesToStorage(result.data)
    }, [result.data])
    return result
}

export function useLocalMediaProfilesView() {
    return useQuery<LocalMediaProfileViewRead[], Error, LocalMediaProfileViewRead[], readonly ['localMediaProfilesView']>({
        queryKey: ['localMediaProfilesView'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/local-media-profiles/as-view`,
            LocalMediaProfileViewReadSchema.array(),
            signal,
        ),
        refetchOnMount: 'always',
    })
}

export function useLocalMediaProfileView(slug?: string) {
    return useQuery<LocalMediaProfileViewRead, Error, LocalMediaProfileViewRead, readonly ['localMediaProfileView', string | undefined]>({
        queryKey: ['localMediaProfileView', slug] as const,
        enabled: !!slug,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/local-media-profiles/${encodeURIComponent(slug!)}/view`,
            LocalMediaProfileViewReadSchema,
            signal,
        ),
        refetchOnMount: 'always',
    })
}

export function usePodcastDownloadProfiles() {
    return useQuery<PodcastDownloadProfileRead[], Error, PodcastDownloadProfileRead[], readonly ['podcastDownloadProfiles']>({
        queryKey: ['podcastDownloadProfiles'] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/podcast-download-profiles`,
            PodcastDownloadProfileReadSchema.array(),
            signal,
        ),
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
        refetchOnMount: 'always',
    })
}

export function useShows() {
    const result = useQuery(showsQueryOptions())
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
    return useQuery({
        ...showQueryOptions(id, qc),
        enabled: !!id,
    })
}

export function useEpisodePages(
    showSlug?: string,
    opts?: {
        pageSize?: number
        seasonId?: number | null
        enabled?: boolean
    },
) {
    const pageSize = opts?.pageSize ?? 36
    const seasonId = opts?.seasonId
    const result = useLazyCollection<EpisodeReadView, EpisodeReadViewPage>({
        collectionPrefix: episodeQueryKeys.forShow(showSlug),
        queryKey: ['pages', seasonId ?? null] as const,
        initialCount: pageSize,
        batchSize: pageSize,
        enabled: !!showSlug && seasonId !== null && (opts?.enabled ?? true),
        fetchPage: ({cursor, limit}, signal) => fetchEpisodePage(
            showSlug!,
            {
                cursor,
                limit,
                seasonId: seasonId ?? undefined,
            },
            signal,
        ),
    })

    const firstPage = result.data?.pages[0]
    useEffect(() => {
        if (!showSlug || seasonId !== undefined || firstPage === undefined) return
        saveEpisodePreviewToStorage(
            showSlug,
            firstPage.items.slice(0, SHOW_EPISODE_PREVIEW_SIZE),
            Date.now(),
            firstPage.showTotal,
        )
    }, [firstPage, seasonId, showSlug])

    return result
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
    })
}

export function useRecentlyIndexedEpisodes(limit = 7) {
    return useQuery<
        EpisodeIndexedActivityRead[],
        Error,
        EpisodeIndexedActivityRead[],
        readonly ['recentlyIndexedEpisodes', number]
    >({
        queryKey: ['recentlyIndexedEpisodes', limit] as const,
        queryFn: ({signal}) => fetchParsed(
            `${(window as any).appConfig.API_URL}/episodes/as-view/recently-indexed?limit=${limit}`,
            EpisodeIndexedActivityReadSchema.array(),
            signal,
        ),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
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
    return useQuery({
        ...seasonsQueryOptions(showSlug),
        enabled: !!showSlug,
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
        refetchOnMount: 'always',
    })
}

const ACTIVE_OPERATION_STATUSES = new Set(['QUEUED', 'RUNNING', 'WAITING'])

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

function progressMetaString(operation: TaskOperationRead | undefined, key: string): string | null {
    const value = operation?.progressMeta?.[key]
    return typeof value === 'string' ? value : null
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
    return operations.filter((operation) => (
        operation.kind === 'media.download'
        && operation.resourceType === 'media_download'
        && operation.resourceId === mediaDownloadId
    )).sort((left, right) => Date.parse(right.createdAt || '') - Date.parse(left.createdAt || ''))[0]

}

function presentDownload(
    download: MediaDownloadDomainViewRead,
    operation?: TaskOperationRead,
): MediaDownloadViewRead {
    const presentation = presentDownloadProgress(download, operation)
    const status = presentation.status
    const operationError = operation?.status === 'FAILED'
        ? (operation.error || operation.message || null)
        : null
    return {
        ...download,
        formatDownloaded: progressMetaString(operation, 'selected_format') ?? download.formatDownloaded,
        downloadStatus: status,
        presentation,
        operation,
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
        assets: [],
        artifactStatus: 'absent',
        artifactError: null,
        artifactSizeBytes: null,
        automaticRetrySuppressed: false,
        downloadedBytes: null,
        formatDownloaded: null,
        downloadedAt: null,
        firstSuccessfulDownloadAt: null,
        canDelete: true,
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

type MediaDownloadScope =
    | {kind: 'all'}
    | {kind: 'episode'; slug?: string}
    | {kind: 'movie'; slug?: string}
    | {kind: 'show'; slug?: string}

function mediaDownloadScopeKey(scope: MediaDownloadScope) {
    switch (scope.kind) {
        case 'episode':
            return ['episodeDownloads', scope.slug] as const
        case 'movie':
            return ['movieDownloads', scope.slug] as const
        case 'show':
            return ['showDownloads', scope.slug] as const
        default:
            return ['mediaDownloadsView'] as const
    }
}

function mediaDownloadScopeUrl(scope: MediaDownloadScope) {
    const base = `${(window as any).appConfig.API_URL}/media-downloads/as-view`
    if (scope.kind === 'all') return base

    const params = new URLSearchParams()
    if (scope.kind === 'episode' && scope.slug) params.set('episode_slug', scope.slug)
    if (scope.kind === 'movie' && scope.slug) params.set('movie_slug', scope.slug)
    if (scope.kind === 'show' && scope.slug) params.set('show_slug', scope.slug)
    return `${base}?${params}`
}

function operationMatchesMediaDownloadScope(
    operation: TaskOperationRead,
    scope: MediaDownloadScope,
) {
    if (scope.kind === 'all') return true
    if (!scope.slug) return false
    if (scope.kind === 'episode') return contextString(operation, 'episode_slug') === scope.slug
    if (scope.kind === 'movie') return contextString(operation, 'movie_slug') === scope.slug
    return contextString(operation, 'show_slug') === scope.slug
}

function useMediaDownloadPresentation(scope: MediaDownloadScope) {
    const enabled = scope.kind === 'all' || Boolean(scope.slug)
    const domainQuery = useQuery({
        queryKey: mediaDownloadScopeKey(scope),
        enabled,
        queryFn: async ({signal}) => {
            const value = await fetchJSON<unknown[]>(
                mediaDownloadScopeUrl(scope),
                signal,
            )
            return MediaDownloadViewReadSchema.array().parse(value)
        },
        refetchOnMount: 'always',
    })
    const {data: pullData} = useFrontendPuller()
    const operations = (pullData?.operations ?? []).filter(
        (operation) => operationMatchesMediaDownloadScope(operation, scope),
    )

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

    return {
        ...domainQuery,
        data,
        hasDomainData: domainQuery.data !== undefined,
    }
}

export function useEpisodeDownloads(episodeSlug?: string) {
    return useMediaDownloadPresentation({kind: 'episode', slug: episodeSlug})
}

export function useMovieDownloads(movieSlug?: string) {
    return useMediaDownloadPresentation({kind: 'movie', slug: movieSlug})
}

export function useShowDownloads(showSlug?: string) {
    return useMediaDownloadPresentation({kind: 'show', slug: showSlug})
}

export function useMediaDownloadsView() {
    return useMediaDownloadPresentation({kind: 'all'})
}


export type MediaDownloadCollectionOrder = 'workflow' | 'recent'

export type MediaDownloadCollectionQuery = {
    statuses?: readonly string[]
    order?: MediaDownloadCollectionOrder
    initialCount?: number
    batchSize?: number
    enabled?: boolean
}

const MEDIA_DOWNLOAD_COLLECTION_PREFIX = ['mediaDownloads'] as const

// Temporary experiment: leave download ordering to backend-paginated results.
// Set back to true to restore local reorder/optimistic insertion behavior.
const ENABLE_FRONTEND_DOWNLOAD_REORDERING = false
const ACTIVE_OR_QUEUED_DOWNLOAD_STATUSES = new Set([
    'pending', 'downloading', 'preparing', 'waiting', 'canceling', 'local_processing',
])

export function compareMediaDownloadWorkflowOrder(left: MediaDownloadViewRead, right: MediaDownloadViewRead): number {
    const leftStatus = String(left.downloadStatus)
    const rightStatus = String(right.downloadStatus)
    const activeStatuses = new Set(['downloading', 'preparing', 'waiting', 'canceling', 'local_processing'])
    const leftActive = activeStatuses.has(leftStatus)
    const rightActive = activeStatuses.has(rightStatus)
    if (leftActive !== rightActive) return leftActive ? -1 : 1

    const leftQueued = leftStatus === 'pending'
    const rightQueued = rightStatus === 'pending'
    if (leftQueued !== rightQueued) return leftQueued ? -1 : 1

    if (leftQueued && rightQueued) {
        if (left.queuePosition == null && right.queuePosition != null) return -1
        if (left.queuePosition != null && right.queuePosition == null) return 1
        if (left.queuePosition != null && right.queuePosition != null) {
            const byPosition = left.queuePosition - right.queuePosition
            if (byPosition !== 0) return byPosition
        }
    }

    if (leftActive && rightActive) {
        // Match the backend: the current execution's start takes precedence
        // over the original download record's creation time.
        const activeStart = (download: MediaDownloadViewRead): number => (
            (download.latestTaskStatus === 'RUNNING' ? download.latestTaskStartedAt : null)
            ?? download.startedAt
            ?? operationDate(download.operation?.createdAt)
            ?? download.createdAt
        ).getTime()
        const byStart = activeStart(left) - activeStart(right)
        if (byStart !== 0) return byStart
    }

    // Completed downloads use their last successful download time, while other terminal statuses use ID ordering
    const leftCompletedAt = leftStatus === 'downloaded' || leftStatus === 'redownloaded'
        ? (left.downloadedAt ?? left.createdAt).getTime()
        : 0
    const rightCompletedAt = rightStatus === 'downloaded' || rightStatus === 'redownloaded'
        ? (right.downloadedAt ?? right.createdAt).getTime()
        : 0
    const byDownloadedAt = rightCompletedAt - leftCompletedAt
    return byDownloadedAt || right.id - left.id
}

function mediaDownloadRecentOrder(left: MediaDownloadViewRead, right: MediaDownloadViewRead): number {
    const leftAt = left.finishedAt ?? left.downloadedAt ?? left.createdAt
    const rightAt = right.finishedAt ?? right.downloadedAt ?? right.createdAt
    const byTime = rightAt.getTime() - leftAt.getTime()
    return byTime || right.id - left.id
}

function mediaDownloadStatusFilterContains(
    source: unknown,
    target: readonly string[],
): boolean {
    if (source === null) return true
    if (!Array.isArray(source)) return false
    const sourceStatuses = new Set(
        source.filter((value): value is string => typeof value === 'string'),
    )
    return target.every((status) => sourceStatuses.has(status))
}

export function deriveMediaDownloadCollectionPlaceholder(
    queryClient: QueryClient,
    {
        statuses,
        order,
        initialCount,
        operations = [],
    }: {
        statuses: readonly string[] | undefined
        order: MediaDownloadCollectionOrder
        initialCount: number
        operations?: TaskOperationRead[]
    },
): InfiniteData<
    LazyCollectionPage<MediaDownloadDomainViewRead>,
    LazyCollectionPageRequest
> | undefined {
    if (statuses === undefined) return undefined

    const targetStatuses = [...new Set(statuses)].sort()
    const targetStatusSet = new Set(targetStatuses)
    const candidates = queryClient.getQueryCache().findAll({
        queryKey: [...MEDIA_DOWNLOAD_COLLECTION_PREFIX, 'list'],
    })

    let best: {
        data: InfiniteData<
            LazyCollectionPage<MediaDownloadDomainViewRead>,
            LazyCollectionPageRequest
        >
        matchCount: number
        updatedAt: number
    } | undefined

    for (const query of candidates) {
        const key = query.queryKey
        if (
            key[0] !== MEDIA_DOWNLOAD_COLLECTION_PREFIX[0]
            || key[1] !== 'list'
            || key[3] !== order
            || !mediaDownloadStatusFilterContains(key[2], targetStatuses)
        ) {
            continue
        }

        const sourceStatuses = key[2]
        if (
            Array.isArray(sourceStatuses)
            && sourceStatuses.length === targetStatuses.length
            && targetStatuses.every((status, index) => sourceStatuses[index] === status)
        ) {
            continue
        }

        const source = query.state.data as InfiniteData<
            LazyCollectionPage<MediaDownloadDomainViewRead>,
            LazyCollectionPageRequest
        > | undefined
        if (!source?.pages.length) continue

        const contiguous = contiguousLazyCollectionItems(source.pages)
        if (!contiguous) continue

        const firstPage = source.pages[0]
        const facets = firstPage.facets
        const targetTotal = facets
            ? targetStatuses.reduce((total, status) => total + (facets[status] ?? 0), 0)
            : contiguous.complete
                ? undefined
                : null
        if (targetTotal === null) continue

        const byId = new Map<number, MediaDownloadDomainViewRead>()
        for (const download of contiguous.items) byId.set(download.id, download)
        if (ENABLE_FRONTEND_DOWNLOAD_REORDERING) {
            for (const operation of operations) {
                if (operation.resourceId == null || byId.has(operation.resourceId)) continue
                const synthetic = syntheticDownload(operation)
                if (synthetic) byId.set(synthetic.id, synthetic)
            }
        }

        const matching = [...byId.values()]
            .map((download) => ({
                download,
                presented: presentDownload(
                    download,
                    operationForDownload(operations, download.id),
                ),
            }))
            .filter(({presented}) => targetStatusSet.has(String(presented.downloadStatus)))
        if (ENABLE_FRONTEND_DOWNLOAD_REORDERING) {
            matching.sort((left, right) => (
                order === 'recent'
                    ? mediaDownloadRecentOrder(left.presented, right.presented)
                    : compareMediaDownloadWorkflowOrder(left.presented, right.presented)
            ))
        }

        const total = targetTotal ?? matching.length
        const items = matching.slice(0, Math.min(initialCount, total))
            .map(({download}) => download)

        if (items.length === 0 && total > 0) continue

        const placeholder: InfiniteData<
            LazyCollectionPage<MediaDownloadDomainViewRead>,
            LazyCollectionPageRequest
        > = {
            pages: [{
                items,
                total,
                limit: initialCount,
                nextCursor: null,
                previousCursor: null,
                revision: firstPage.revision,
                facets: firstPage.facets,
                // Bulk-action counts depend on the exact filtered collection and
                // are intentionally left for the authoritative backend response.
                actions: {},
            }],
            pageParams: [{cursor: null, limit: initialCount}],
        }

        const score = items.length
        if (
            best === undefined
            || score > best.matchCount
            || (score === best.matchCount && query.state.dataUpdatedAt > best.updatedAt)
        ) {
            best = {
                data: placeholder,
                matchCount: score,
                updatedAt: query.state.dataUpdatedAt,
            }
        }
    }

    return best?.data
}

export function useMediaDownloadsCollection({
    statuses,
    order = 'workflow',
    initialCount = 50,
    batchSize = 50,
    enabled = true,
}: MediaDownloadCollectionQuery = {}) {
    const normalizedStatuses = useMemo(
        () => downloadStatusesForApi(statuses),
        [statuses],
    )
    const {data: pullData} = useFrontendPuller()
    const operations = (pullData?.operations ?? []).filter(
        (operation) => operation.kind === 'media.download',
    )
    const queryClient = useQueryClient()
    const lastActiveOrderSignature = useRef<string | null>(null)
    const activeOrderSignature = operations
        .filter((operation) => ACTIVE_OPERATION_STATUSES.has(operation.status))
        .map((operation) => `${operation.id}:${operation.status}:${operation.startedAt ?? ''}`)
        .sort()
        .join('|')

    // With local reordering disabled, fetch authoritative backend positions
    // when operations enter/leave the active queue. Progress-only pulls do
    // not change this signature and should not trigger an extra page request.
    useEffect(() => {
        if (
            ENABLE_FRONTEND_DOWNLOAD_REORDERING || !enabled || !pullData
            || (
                normalizedStatuses !== undefined
                && !normalizedStatuses.some((status) => ACTIVE_OR_QUEUED_DOWNLOAD_STATUSES.has(status))
            )
        ) return
        if (lastActiveOrderSignature.current === null) {
            lastActiveOrderSignature.current = activeOrderSignature
            return
        }
        if (lastActiveOrderSignature.current === activeOrderSignature) return
        lastActiveOrderSignature.current = activeOrderSignature
        void queryClient.invalidateQueries({
            queryKey: lazyCollectionQueryKey(
                MEDIA_DOWNLOAD_COLLECTION_PREFIX,
                [normalizedStatuses ?? null, order],
                initialCount,
                batchSize,
            ),
            exact: true,
            refetchType: 'active',
        })
    }, [
        activeOrderSignature, enabled, pullData, queryClient,
        normalizedStatuses, order, initialCount, batchSize,
    ])

    const collection = useLazyCollection<MediaDownloadDomainViewRead>({
        collectionPrefix: MEDIA_DOWNLOAD_COLLECTION_PREFIX,
        queryKey: [normalizedStatuses ?? null, order] as const,
        initialCount,
        batchSize,
        enabled,
        derivePlaceholderData: (queryClient) => deriveMediaDownloadCollectionPlaceholder(
            queryClient,
            {
                statuses: normalizedStatuses,
                order,
                initialCount,
                operations,
            },
        ),
        fetchPage: async ({cursor, limit}, signal) => {
            const params = new URLSearchParams({
                order,
                limit: String(limit),
            })
            if (cursor) params.set('cursor', cursor)
            for (const status of normalizedStatuses ?? []) params.append('status', status)
            return MediaDownloadPageReadSchema.parse(await fetchJSON<unknown>(
                `${(window as any).appConfig.API_URL}/media-downloads/as-view/page?${params}`,
                signal,
            ))
        },
    })

    const data = useMemo(() => {
        const downloads = new Map<number, MediaDownloadDomainViewRead>()
        for (const download of collection.items) downloads.set(download.id, download)

        if (ENABLE_FRONTEND_DOWNLOAD_REORDERING) {
            for (const operation of operations) {
                if (operation.resourceId == null || downloads.has(operation.resourceId)) continue
                const synthetic = syntheticDownload(operation)
                if (synthetic) downloads.set(synthetic.id, synthetic)
            }
        }

        const presented = [...downloads.values()]
            .map((download) => presentDownload(
                download,
                operationForDownload(operations, download.id),
            ))
            .filter((download) => (
                normalizedStatuses === undefined
                || normalizedStatuses.includes(String(download.downloadStatus))
            ))

        if (ENABLE_FRONTEND_DOWNLOAD_REORDERING) {
            presented.sort(order === 'recent' ? mediaDownloadRecentOrder : compareMediaDownloadWorkflowOrder)
        }
        return presented
    }, [collection.items, normalizedStatuses, operations, order])

    return {
        ...collection,
        data,
    }
}

export function applyMediaDownloadQueuePositions(
    queryClient: QueryClient,
    positions: Record<number, number>,
) {
    updateLazyCollectionEntities<MediaDownloadDomainViewRead>(
        queryClient,
        MEDIA_DOWNLOAD_COLLECTION_PREFIX,
        (download) => {
            const queuePosition = positions[download.id] ?? null
            if ((download.queuePosition ?? null) === queuePosition) return download
            return {...download, queuePosition}
        },
    )
}

// Prefetch core data to warm the cache on app start
export function prefetchCoreData(qc: QueryClient) {
    void qc
        .prefetchQuery(showsQueryOptions())
        .then(() => {
            const shows = qc.getQueryData<ShowRead[]>(showsQueryOptions().queryKey)
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
