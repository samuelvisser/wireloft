// Lightweight browser persistence for data that materially improves cold-page loads.
// Show caches retain only a compact five-episode preview; full show histories are paged from the
// local API as the user scrolls. Episode detail pages still fetch the complete episode record.

import {LocalMediaProfileRead, LocalMediaProfileReadSchema} from "../types/schemas/local_media_profile";
import {EpisodeReadView, EpisodeReadViewSchema} from "../types/schemas/episode";
import {SeasonRead, SeasonReadSchema} from "../types/schemas/season";
import {ShowRead, ShowReadSchema} from "../types/schemas/show";

const STORAGE_PREFIX = 'wl_rq_v1:'
const KEY_SHOWS = STORAGE_PREFIX + 'shows'
const KEY_PROFILES = STORAGE_PREFIX + 'localMediaProfiles'

const SHOW_CACHE_PREFIX = 'wl_show_cache_v3:'
const SHOW_CACHE_VERSION = 4
const KEY_EPISODES_PREFIX = SHOW_CACHE_PREFIX + 'episodes:'
const KEY_EPISODES_META_PREFIX = SHOW_CACHE_PREFIX + 'episodes-meta:'
const KEY_SEASONS_PREFIX = SHOW_CACHE_PREFIX + 'seasons:'
const KEY_SEASONS_META_PREFIX = SHOW_CACHE_PREFIX + 'seasons-meta:'

type CacheMetadata = {
  version: number
  fetchedAt: number
  total?: number
}

type MemoryEntry<T> = {
  data: T
  fetchedAt: number
  total?: number
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
  if (
    record.total !== undefined
    && (typeof record.total !== 'number' || !Number.isInteger(record.total) || record.total < 0)
  ) return undefined
  return {
    version: SHOW_CACHE_VERSION,
    fetchedAt: record.fetchedAt,
    total: record.total as number | undefined,
  }
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

function seasonsStorageKey(showSlug: string) {
  return showCacheKey(KEY_SEASONS_PREFIX, showSlug)
}

function seasonsMetadataKey(showSlug: string) {
  return showCacheKey(KEY_SEASONS_META_PREFIX, showSlug)
}

function cacheMetadata(fetchedAt: number, total?: number): CacheMetadata {
  return {version: SHOW_CACHE_VERSION, fetchedAt, total}
}

function compactEpisodes(data: EpisodeReadView[]): EpisodeReadView[] {
  return data.map((episode) => ({
    id: episode.id,
    showId: episode.showId,
    seasonId: episode.seasonId,
    index: episode.index,
    episodeIdentifier: episode.episodeIdentifier,
    dwEpisodeNumber: episode.dwEpisodeNumber,
    episodeType: episode.episodeType,
    episodeExtraType: episode.episodeExtraType,
    episodeNumber: episode.episodeNumber,
    episodeSubNumber: episode.episodeSubNumber,
    episodeLabel: episode.episodeLabel,
    slug: episode.slug,
    title: episode.title,
    publishStatus: episode.publishStatus,
    thumbnailLandscapePath: episode.thumbnailLandscapePath ?? null,
    thumbnailPortraitPath: episode.thumbnailPortraitPath ?? null,
    thumbnailSquarePath: episode.thumbnailSquarePath ?? null,
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

  const metadata = parseCacheMetadata(safeGetItem(episodesMetadataKey(showSlug)))
  if (metadata === undefined) return undefined

  const cached = parseStored(safeGetItem(episodesStorageKey(showSlug)), EpisodeReadViewSchema.array())
  if (cached !== undefined) {
    episodeMemoryCache.set(showSlug, {
      data: cached,
      fetchedAt: metadata.fetchedAt,
      total: metadata.total,
    })
    return cached
  }

  return undefined
}

export function getEpisodesCacheFetchedAt(showSlug: string): number | undefined {
  const memory = episodeMemoryCache.get(showSlug)
  if (memory) return memory.fetchedAt > 0 ? memory.fetchedAt : undefined

  return parseCacheMetadata(safeGetItem(episodesMetadataKey(showSlug)))?.fetchedAt
}

export function getEpisodesCacheTotal(showSlug: string): number | undefined {
  const memory = episodeMemoryCache.get(showSlug)
  if (memory?.total !== undefined) return memory.total

  return parseCacheMetadata(safeGetItem(episodesMetadataKey(showSlug)))?.total
}

export function saveEpisodesToStorage(
  showSlug: string,
  data: EpisodeReadView[] | undefined,
  fetchedAt?: number,
  total?: number,
) {
  if (data === undefined) {
    removeEpisodesFromStorage(showSlug)
    return
  }

  const existing = episodeMemoryCache.get(showSlug)
  const effectiveFetchedAt = fetchedAt ?? existing?.fetchedAt ?? Date.now()
  const effectiveTotal = total ?? existing?.total
  if (
    existing?.data === data
    && existing.fetchedAt === effectiveFetchedAt
    && existing.total === effectiveTotal
  ) return

  episodeMemoryCache.set(showSlug, {
    data,
    fetchedAt: effectiveFetchedAt,
    total: effectiveTotal,
  })

  const persisted = safeSetItem(episodesStorageKey(showSlug), JSON.stringify(compactEpisodes(data)))
  if (persisted) {
    safeSetItem(
      episodesMetadataKey(showSlug),
      JSON.stringify(cacheMetadata(effectiveFetchedAt, effectiveTotal)),
    )
  }
}

export function removeEpisodesFromStorage(showSlug: string) {
  episodeMemoryCache.delete(showSlug)
  safeRemoveItem(episodesStorageKey(showSlug))
  safeRemoveItem(episodesMetadataKey(showSlug))
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
