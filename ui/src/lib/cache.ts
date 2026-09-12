// Lightweight browser persistence for React Query data that materially improves cold-page loads.
// Show episode lists deliberately use a compact representation so long-running shows do not exhaust
// localStorage with detail-only fields such as descriptions. The full episode is still fetched when
// an episode detail page opens; show grids use the compact EpisodeReadView representation.

import {LocalMediaProfileRead, LocalMediaProfileReadSchema} from "../types/schemas/local_media_profile";
import {EpisodeReadSchema, EpisodeReadView, EpisodeReadViewSchema} from "../types/schemas/episode";
import {SeasonRead, SeasonReadSchema} from "../types/schemas/season";
import {ShowRead, ShowReadSchema} from "../types/schemas/show";

const STORAGE_PREFIX = 'wl_rq_v1:'
const KEY_SHOWS = STORAGE_PREFIX + 'shows'
const KEY_PROFILES = STORAGE_PREFIX + 'localMediaProfiles'
const LEGACY_KEY_EPISODES_PREFIX = STORAGE_PREFIX + 'episodes:'

const SHOW_CACHE_PREFIX = 'wl_show_cache_v2:'
const SHOW_CACHE_VERSION = 1
const KEY_EPISODES_PREFIX = SHOW_CACHE_PREFIX + 'episodes:'
const KEY_EPISODES_META_PREFIX = SHOW_CACHE_PREFIX + 'episodes-meta:'
const KEY_SEASONS_PREFIX = SHOW_CACHE_PREFIX + 'seasons:'
const KEY_SEASONS_META_PREFIX = SHOW_CACHE_PREFIX + 'seasons-meta:'

type CacheMetadata = {
  version: number
  fetchedAt: number
}

type MemoryEntry<T> = {
  data: T
  fetchedAt: number
}

const episodeMemoryCache = new Map<string, MemoryEntry<EpisodeReadView[]>>()
const seasonMemoryCache = new Map<string, MemoryEntry<SeasonRead[]>>()

function safeJsonParse(raw: string | null): unknown | undefined {
  if (!raw) return undefined
  try {
    return JSON.parse(raw)
  } catch {
    return undefined
  }
}

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSetItem(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

function safeRemoveItem(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {
    // Browser storage is an optimization only.
  }
}

function parseStored<T>(raw: string | null, schema: {safeParse(value: unknown): {success: boolean; data?: T}}): T | undefined {
  const value = safeJsonParse(raw)
  if (value === undefined) return undefined
  const parsed = schema.safeParse(value)
  return parsed.success ? parsed.data : undefined
}

function parseCacheMetadata(raw: string | null): CacheMetadata | undefined {
  const value = safeJsonParse(raw)
  if (!value || typeof value !== 'object') return undefined
  const record = value as Record<string, unknown>
  if (record.version !== SHOW_CACHE_VERSION) return undefined
  if (typeof record.fetchedAt !== 'number' || !Number.isFinite(record.fetchedAt)) return undefined
  return {version: SHOW_CACHE_VERSION, fetchedAt: record.fetchedAt}
}

function showCacheKey(prefix: string, showSlug: string) {
  return prefix + encodeURIComponent(showSlug)
}

function episodesStorageKey(showSlug: string) {
  return showCacheKey(KEY_EPISODES_PREFIX, showSlug)
}

function episodesMetadataKey(showSlug: string) {
  return showCacheKey(KEY_EPISODES_META_PREFIX, showSlug)
}

function legacyEpisodesStorageKey(showSlug: string) {
  return showCacheKey(LEGACY_KEY_EPISODES_PREFIX, showSlug)
}

function seasonsStorageKey(showSlug: string) {
  return showCacheKey(KEY_SEASONS_PREFIX, showSlug)
}

function seasonsMetadataKey(showSlug: string) {
  return showCacheKey(KEY_SEASONS_META_PREFIX, showSlug)
}

function cacheMetadata(fetchedAt: number): CacheMetadata {
  return {version: SHOW_CACHE_VERSION, fetchedAt}
}

function compactEpisodes(data: EpisodeReadView[]): EpisodeReadView[] {
  return data.map((episode) => ({
    id: episode.id,
    showId: episode.showId,
    seasonId: episode.seasonId,
    index: episode.index,
    episodeIdentifier: episode.episodeIdentifier,
    slug: episode.slug,
    title: episode.title,
    publishStatus: episode.publishStatus,
    thumbnailPortraitPath: episode.thumbnailPortraitPath ?? null,
  }))
}

export function loadShowsFromStorage(): ShowRead[] | undefined {
  return parseStored(safeGetItem(KEY_SHOWS), ShowReadSchema.array())
}

export function saveShowsToStorage(data: ShowRead[] | undefined) {
  if (!data) {
    safeRemoveItem(KEY_SHOWS)
    return
  }
  safeSetItem(KEY_SHOWS, JSON.stringify(data))
}

/** Return a persisted show-grid episode list synchronously so ShowPage can paint before revalidation. */
export function loadEpisodesFromStorage(showSlug?: string): EpisodeReadView[] | undefined {
  if (!showSlug) return undefined

  const memory = episodeMemoryCache.get(showSlug)
  if (memory) return memory.data

  const cached = parseStored(safeGetItem(episodesStorageKey(showSlug)), EpisodeReadViewSchema.array())
  if (cached !== undefined) {
    const fetchedAt = getEpisodesCacheFetchedAt(showSlug) ?? 0
    episodeMemoryCache.set(showSlug, {data: cached, fetchedAt})
    return cached
  }

  // Compatibility with the old full-object cache. It has no trustworthy timestamp, so startup
  // treats it as stale and refreshes it into the compact v2 representation in the background.
  const legacy = parseStored(safeGetItem(legacyEpisodesStorageKey(showSlug)), EpisodeReadSchema.array())
  if (legacy !== undefined) {
    const compact = compactEpisodes(legacy)
    episodeMemoryCache.set(showSlug, {data: compact, fetchedAt: 0})
    return compact
  }

  return undefined
}

export function getEpisodesCacheFetchedAt(showSlug: string): number | undefined {
  const memory = episodeMemoryCache.get(showSlug)
  if (memory) return memory.fetchedAt > 0 ? memory.fetchedAt : undefined

  if (safeGetItem(episodesStorageKey(showSlug)) === null) return undefined
  return parseCacheMetadata(safeGetItem(episodesMetadataKey(showSlug)))?.fetchedAt
}

export function saveEpisodesToStorage(
  showSlug: string,
  data: EpisodeReadView[] | undefined,
  fetchedAt?: number,
) {
  if (data === undefined) {
    removeEpisodesFromStorage(showSlug)
    return
  }

  const existing = episodeMemoryCache.get(showSlug)
  const effectiveFetchedAt = fetchedAt ?? existing?.fetchedAt ?? Date.now()
  if (existing?.data === data && existing.fetchedAt === effectiveFetchedAt) return

  episodeMemoryCache.set(showSlug, {data, fetchedAt: effectiveFetchedAt})

  const persisted = safeSetItem(episodesStorageKey(showSlug), JSON.stringify(compactEpisodes(data)))
  if (persisted) {
    safeSetItem(episodesMetadataKey(showSlug), JSON.stringify(cacheMetadata(effectiveFetchedAt)))
    safeRemoveItem(legacyEpisodesStorageKey(showSlug))
  }
}

export function removeEpisodesFromStorage(showSlug: string) {
  episodeMemoryCache.delete(showSlug)
  safeRemoveItem(episodesStorageKey(showSlug))
  safeRemoveItem(episodesMetadataKey(showSlug))
  safeRemoveItem(legacyEpisodesStorageKey(showSlug))
}

export function loadSeasonsFromStorage(showSlug?: string): SeasonRead[] | undefined {
  if (!showSlug) return undefined

  const memory = seasonMemoryCache.get(showSlug)
  if (memory) return memory.data

  const cached = parseStored(safeGetItem(seasonsStorageKey(showSlug)), SeasonReadSchema.array())
  if (cached === undefined) return undefined

  const fetchedAt = getSeasonsCacheFetchedAt(showSlug) ?? 0
  seasonMemoryCache.set(showSlug, {data: cached, fetchedAt})
  return cached
}

export function getSeasonsCacheFetchedAt(showSlug: string): number | undefined {
  const memory = seasonMemoryCache.get(showSlug)
  if (memory) return memory.fetchedAt > 0 ? memory.fetchedAt : undefined

  if (safeGetItem(seasonsStorageKey(showSlug)) === null) return undefined
  return parseCacheMetadata(safeGetItem(seasonsMetadataKey(showSlug)))?.fetchedAt
}

export function saveSeasonsToStorage(
  showSlug: string,
  data: SeasonRead[] | undefined,
  fetchedAt?: number,
) {
  if (data === undefined) {
    removeSeasonsFromStorage(showSlug)
    return
  }

  const existing = seasonMemoryCache.get(showSlug)
  const effectiveFetchedAt = fetchedAt ?? existing?.fetchedAt ?? Date.now()
  if (existing?.data === data && existing.fetchedAt === effectiveFetchedAt) return

  seasonMemoryCache.set(showSlug, {data, fetchedAt: effectiveFetchedAt})
  const persisted = safeSetItem(seasonsStorageKey(showSlug), JSON.stringify(data))
  if (persisted) {
    safeSetItem(seasonsMetadataKey(showSlug), JSON.stringify(cacheMetadata(effectiveFetchedAt)))
  }
}

export function removeSeasonsFromStorage(showSlug: string) {
  seasonMemoryCache.delete(showSlug)
  safeRemoveItem(seasonsStorageKey(showSlug))
  safeRemoveItem(seasonsMetadataKey(showSlug))
}

export function loadProfilesFromStorage(): LocalMediaProfileRead[] | undefined {
  return parseStored(safeGetItem(KEY_PROFILES), LocalMediaProfileReadSchema.array())
}

export function saveProfilesToStorage(data: LocalMediaProfileRead[] | undefined) {
  if (!data) {
    safeRemoveItem(KEY_PROFILES)
    return
  }
  safeSetItem(KEY_PROFILES, JSON.stringify(data))
}
