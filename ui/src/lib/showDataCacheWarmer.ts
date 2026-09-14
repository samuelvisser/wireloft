import {QueryClient} from '@tanstack/react-query'

import {
  getEpisodesCacheFetchedAt,
  getSeasonsCacheFetchedAt,
  loadEpisodesFromStorage,
  loadSeasonsFromStorage,
  saveEpisodesToStorage,
  saveSeasonsToStorage,
  saveShowsToStorage,
} from './cache'
import {EpisodeReadView, EpisodeReadViewSchema} from '../types/schemas/episode'
import {SeasonRead, SeasonReadSchema} from '../types/schemas/season'
import {ShowRead, ShowReadSchema} from '../types/schemas/show'

const SHOW_DATA_MAX_AGE_MS = 24 * 60 * 60 * 1000
const SHOW_WARM_CONCURRENCY = 2

async function fetchParsed<T>(
  url: string,
  schema: {parse(value: unknown): T},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {signal, credentials: 'include'})
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return schema.parse(await response.json())
}

function apiBase() {
  return ((window as any).appConfig?.API_URL || '/api').replace(/\/+$/, '')
}

function isFresh(fetchedAt: number | undefined) {
  if (fetchedAt === undefined) return false
  return Date.now() - fetchedAt < SHOW_DATA_MAX_AGE_MS
}

function newestTimestamp(...timestamps: Array<number | undefined>) {
  return Math.max(0, ...timestamps.map((value) => value ?? 0)) || undefined
}

function showSlugFromCurrentRoute(): string | undefined {
  if (typeof window === 'undefined') return undefined
  const match = window.location.pathname.match(/^\/show\/([^/]+)\/?$/)
  if (!match) return undefined
  try {
    return decodeURIComponent(match[1])
  } catch {
    return match[1]
  }
}

/**
 * Hydrate only the show that is being opened directly. Parsing every persisted episode list at
 * startup would defeat the purpose of the background warmer, while parsing one requested show is
 * cheap and lets a cold browser reload render its episode cards immediately.
 */
export function hydrateCurrentShowRouteCache(queryClient: QueryClient): void {
  const showSlug = showSlugFromCurrentRoute()
  if (!showSlug) return

  const episodes = loadEpisodesFromStorage(showSlug)
  if (episodes !== undefined) {
    queryClient.setQueryData(
      ['episodes', showSlug, undefined],
      episodes,
      {updatedAt: getEpisodesCacheFetchedAt(showSlug) ?? 0},
    )
  }

  const seasons = loadSeasonsFromStorage(showSlug)
  if (seasons !== undefined) {
    queryClient.setQueryData(
      ['seasons', showSlug],
      seasons,
      {updatedAt: getSeasonsCacheFetchedAt(showSlug) ?? 0},
    )
  }
}

/** Season lists are small, and ShowPage needs them before it can render a seasonal episode grid. */
export function hydrateCachedSeasonQueries(queryClient: QueryClient, shows: ShowRead[]): void {
  for (const show of shows) {
    if (show.episodeIdentifier !== 'seasonal') continue
    const seasons = loadSeasonsFromStorage(show.slug)
    if (seasons === undefined) continue
    const cachedAt = getSeasonsCacheFetchedAt(show.slug) ?? 0
    const queryUpdatedAt = queryClient.getQueryState(['seasons', show.slug])?.dataUpdatedAt ?? 0
    if (queryUpdatedAt >= cachedAt && queryClient.getQueryData(['seasons', show.slug]) !== undefined) continue
    queryClient.setQueryData(['seasons', show.slug], seasons, {updatedAt: cachedAt})
  }
}

async function warmEpisodes(queryClient: QueryClient, show: ShowRead) {
  const queryKey = ['episodes', show.slug, undefined] as const
  const queryUpdatedAt = queryClient.getQueryState(queryKey)?.dataUpdatedAt
  const cachedAt = getEpisodesCacheFetchedAt(show.slug)
  if (isFresh(newestTimestamp(queryUpdatedAt, cachedAt))) return

  await queryClient.prefetchQuery({
    queryKey,
    staleTime: 0,
    queryFn: ({signal}) => fetchParsed(
      `${apiBase()}/episodes/as-view/by-show-slug/${encodeURIComponent(show.slug)}`,
      EpisodeReadViewSchema.array(),
      signal,
    ),
  })
}

async function warmSeasons(queryClient: QueryClient, show: ShowRead) {
  if (show.episodeIdentifier !== 'seasonal') return

  const queryKey = ['seasons', show.slug] as const
  const cachedAt = getSeasonsCacheFetchedAt(show.slug)
  const queryUpdatedAt = queryClient.getQueryState(queryKey)?.dataUpdatedAt
  const newest = newestTimestamp(queryUpdatedAt, cachedAt)
  if (isFresh(newest)) return

  await queryClient.prefetchQuery({
    queryKey,
    staleTime: 0,
    queryFn: ({signal}) => fetchParsed(
      `${apiBase()}/shows/${encodeURIComponent(show.slug)}/seasons`,
      SeasonReadSchema.array(),
      signal,
    ),
  })
}

async function yieldToBrowser() {
  await new Promise<void>((resolve) => setTimeout(resolve, 0))
}

async function warmShowsWithLimitedConcurrency(
  queryClient: QueryClient,
  shows: ShowRead[],
) {
  let nextIndex = 0

  const worker = async () => {
    while (nextIndex < shows.length) {
      const show = shows[nextIndex]
      nextIndex += 1
      try {
        await warmSeasons(queryClient, show)
        await warmEpisodes(queryClient, show)
      } catch {
        // Cache warming is opportunistic. Foreground queries still surface errors normally.
      }
      await yieldToBrowser()
    }
  }

  const workerCount = Math.min(SHOW_WARM_CONCURRENCY, shows.length)
  await Promise.all(Array.from({length: workerCount}, () => worker()))
}

async function warmShowDataCache(queryClient: QueryClient) {
  let shows = queryClient.getQueryData<ShowRead[]>(['shows']) ?? []
  hydrateCachedSeasonQueries(queryClient, shows)

  try {
    // Always resolve the current show list in the background so newly-added shows are included.
    shows = await queryClient.fetchQuery({
      queryKey: ['shows'] as const,
      staleTime: 0,
      queryFn: ({signal}) => fetchParsed(
        `${apiBase()}/shows`,
        ShowReadSchema.array(),
        signal,
      ),
    })
    saveShowsToStorage(shows)
    hydrateCachedSeasonQueries(queryClient, shows)
  } catch {
    // If the API is temporarily unavailable, cached show metadata is still useful for warming.
  }

  if (shows.length === 0) return
  await warmShowsWithLimitedConcurrency(queryClient, shows)
}

let persistenceInstalled = false

/** Persist successful show-list episode/season query results, including normal foreground refreshes. */
export function installShowDataQueryPersistence(queryClient: QueryClient): void {
  if (persistenceInstalled) return
  persistenceInstalled = true

  const lastPersistedAt = new Map<string, number>()
  queryClient.getQueryCache().subscribe((event) => {
    const query = event.query
    const state = query.state
    if (state.status !== 'success' || state.dataUpdatedAt <= 0 || !Array.isArray(state.data)) return

    const [kind, showSlug, limit] = query.queryKey
    if (typeof showSlug !== 'string') return

    if (kind === 'episodes' && limit === undefined) {
      const marker = `episodes:${showSlug}`
      if (lastPersistedAt.get(marker) === state.dataUpdatedAt) return
      lastPersistedAt.set(marker, state.dataUpdatedAt)
      saveEpisodesToStorage(showSlug, state.data as EpisodeReadView[], state.dataUpdatedAt)
      return
    }

    if (kind === 'seasons') {
      const marker = `seasons:${showSlug}`
      if (lastPersistedAt.get(marker) === state.dataUpdatedAt) return
      lastPersistedAt.set(marker, state.dataUpdatedAt)
      saveSeasonsToStorage(showSlug, state.data as SeasonRead[], state.dataUpdatedAt)
    }
  })
}

type IdleCapableWindow = Window & {
  requestIdleCallback?: (callback: () => void, options?: {timeout: number}) => number
}

function scheduleAfterFirstPaint(run: () => void) {
  const idleWindow = window as IdleCapableWindow
  if (idleWindow.requestIdleCallback) {
    idleWindow.requestIdleCallback(run, {timeout: 750})
  } else {
    window.setTimeout(run, 0)
  }
}

/** Start after the first paint, then keep network/parse pressure low with a two-request worker pool. */
export function scheduleShowDataCacheWarm(queryClient: QueryClient): void {
  const run = () => {
    void warmShowDataCache(queryClient)
  }

  if (typeof window === 'undefined') {
    run()
    return
  }

  const schedule = () => scheduleAfterFirstPaint(run)

  if (document.visibilityState !== 'hidden') {
    schedule()
    return
  }

  const startWhenVisible = () => {
    if (document.visibilityState === 'hidden') return
    document.removeEventListener('visibilitychange', startWhenVisible)
    schedule()
  }
  document.addEventListener('visibilitychange', startWhenVisible)
}
