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
import {
  episodesQueryOptions,
  seasonsQueryOptions,
  showsQueryOptions,
} from './showQueryOptions'
import {EpisodeReadView} from '../types/schemas/episode'
import {SeasonRead} from '../types/schemas/season'
import {ShowRead} from '../types/schemas/show'

const SHOW_DATA_MAX_AGE_MS = 24 * 60 * 60 * 1000
const SHOW_WARM_CONCURRENCY = 2

function isFresh(fetchedAt: number | undefined) {
  if (fetchedAt === undefined) return false
  return Date.now() - fetchedAt < SHOW_DATA_MAX_AGE_MS
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
 * Hydrate only the show that is being opened directly. Parsing every persisted episode list before
 * the initial render would delay startup, while parsing one requested show is cheap and lets a cold
 * browser reload render its episode cards immediately.
 */
export function hydrateCurrentShowRouteCache(queryClient: QueryClient): void {
  const showSlug = showSlugFromCurrentRoute()
  if (!showSlug) return

  const episodeOptions = episodesQueryOptions(showSlug)
  const episodes = loadEpisodesFromStorage(showSlug)
  if (episodes !== undefined) {
    queryClient.setQueryData(
      episodeOptions.queryKey,
      episodes,
      {updatedAt: getEpisodesCacheFetchedAt(showSlug) ?? 0},
    )
  }

  const seasonOptions = seasonsQueryOptions(showSlug)
  const seasons = loadSeasonsFromStorage(showSlug)
  if (seasons !== undefined) {
    queryClient.setQueryData(
      seasonOptions.queryKey,
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
    const queryKey = seasonsQueryOptions(show.slug).queryKey
    const queryUpdatedAt = queryClient.getQueryState(queryKey)?.dataUpdatedAt ?? 0
    if (queryUpdatedAt >= cachedAt && queryClient.getQueryData(queryKey) !== undefined) continue
    queryClient.setQueryData(queryKey, seasons, {updatedAt: cachedAt})
  }
}

async function warmEpisodes(queryClient: QueryClient, show: ShowRead) {
  const options = episodesQueryOptions(show.slug)
  const queryData = queryClient.getQueryData(options.queryKey)
  const queryUpdatedAt = queryClient.getQueryState(options.queryKey)?.dataUpdatedAt
  const cachedAt = getEpisodesCacheFetchedAt(show.slug)

  // If the cached data is recent, do put it in memory so it can immediately be used
  if (
    cachedAt !== undefined
    && isFresh(cachedAt)
    && (queryData === undefined || (queryUpdatedAt ?? 0) < cachedAt)
  ) {
    const cachedEpisodes = loadEpisodesFromStorage(show.slug)
    if (cachedEpisodes !== undefined) {
      queryClient.setQueryData(options.queryKey, cachedEpisodes, {updatedAt: cachedAt})
      return
    }
  }

  if (queryData !== undefined && isFresh(queryUpdatedAt)) return

  // Persist data fetched by the warmer directly. The query-cache subscription below still handles
  // normal foreground refreshes, but warming should not depend on that side effect being installed.
  const episodes = await queryClient.fetchQuery({...options, staleTime: 0})
  const fetchedAt = queryClient.getQueryState(options.queryKey)?.dataUpdatedAt ?? Date.now()
  saveEpisodesToStorage(show.slug, episodes, fetchedAt)
}

async function warmSeasons(queryClient: QueryClient, show: ShowRead) {
  if (show.episodeIdentifier !== 'seasonal') return

  const options = seasonsQueryOptions(show.slug)
  const cachedAt = getSeasonsCacheFetchedAt(show.slug)
  const queryData = queryClient.getQueryData(options.queryKey)
  const queryUpdatedAt = queryClient.getQueryState(options.queryKey)?.dataUpdatedAt
  if (queryData !== undefined && isFresh(queryUpdatedAt ?? cachedAt)) return

  const seasons = await queryClient.fetchQuery({...options, staleTime: 0})
  const fetchedAt = queryClient.getQueryState(options.queryKey)?.dataUpdatedAt ?? Date.now()
  saveSeasonsToStorage(show.slug, seasons, fetchedAt)
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
  const showOptions = showsQueryOptions()
  let shows = queryClient.getQueryData<ShowRead[]>(showOptions.queryKey) ?? []
  hydrateCachedSeasonQueries(queryClient, shows)

  try {
    // Always resolve the current show list in the background so newly-added shows are included.
    shows = await queryClient.fetchQuery({...showOptions, staleTime: 0})
    saveShowsToStorage(shows)
    hydrateCachedSeasonQueries(queryClient, shows)
  } catch {
    // If the API is temporarily unavailable, cached show metadata is still useful for warming.
  }

  if (shows.length === 0) return
  await warmShowsWithLimitedConcurrency(queryClient, shows)
}

const persistenceInstalledFor = new WeakSet<QueryClient>()

/** Persist successful show-list episode/season query results, including normal foreground refreshes. */
export function installShowDataQueryPersistence(queryClient: QueryClient): void {
  if (persistenceInstalledFor.has(queryClient)) return
  persistenceInstalledFor.add(queryClient)

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
