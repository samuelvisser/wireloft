// Simple localStorage persistence for React Query data we care about
// Focuses on shows, show episodes, and local media profiles to prevent flicker on reload

import {LocalMediaProfileRead, LocalMediaProfileReadSchema} from "../types/schemas/local_media_profile";
import {EpisodeRead, EpisodeReadSchema} from "../types/schemas/episode";
import {ShowRead, ShowReadSchema} from "../types/schemas/show";

const STORAGE_PREFIX = 'wl_rq_v1:'
const KEY_SHOWS = STORAGE_PREFIX + 'shows'
const KEY_PROFILES = STORAGE_PREFIX + 'localMediaProfiles'
const KEY_EPISODES_PREFIX = STORAGE_PREFIX + 'episodes:'

function safeJsonParse(raw: string | null): unknown | undefined {
  if (!raw) return undefined
  try {
    return JSON.parse(raw)
  } catch {
    return undefined
  }
}

function parseStored<T>(raw: string | null, schema: {safeParse(value: unknown): {success: boolean; data?: T}}): T | undefined {
  const value = safeJsonParse(raw)
  if (value === undefined) return undefined
  const parsed = schema.safeParse(value)
  return parsed.success ? parsed.data : undefined
}

function episodesStorageKey(showSlug: string) {
  return KEY_EPISODES_PREFIX + encodeURIComponent(showSlug)
}

export function loadShowsFromStorage(): ShowRead[] | undefined {
  return parseStored(localStorage.getItem(KEY_SHOWS), ShowReadSchema.array())
}

export function saveShowsToStorage(data: ShowRead[] | undefined) {
  try {
    if (!data) {
      localStorage.removeItem(KEY_SHOWS)
    } else {
      localStorage.setItem(KEY_SHOWS, JSON.stringify(data))
    }
  } catch {
    // ignore quota or serialization errors
  }
}

export function loadEpisodesFromStorage(showSlug?: string): EpisodeRead[] | undefined {
  if (!showSlug) return undefined
  return parseStored(localStorage.getItem(episodesStorageKey(showSlug)), EpisodeReadSchema.array())
}

export function saveEpisodesToStorage(showSlug: string, data: EpisodeRead[] | undefined) {
  try {
    const key = episodesStorageKey(showSlug)
    if (data === undefined) {
      localStorage.removeItem(key)
    } else {
      localStorage.setItem(key, JSON.stringify(data))
    }
  } catch {
    // ignore quota or serialization errors
  }
}

export function removeEpisodesFromStorage(showSlug: string) {
  try {
    localStorage.removeItem(episodesStorageKey(showSlug))
  } catch {
    // ignore storage access errors
  }
}

export function loadProfilesFromStorage(): LocalMediaProfileRead[] | undefined {
  return parseStored(localStorage.getItem(KEY_PROFILES), LocalMediaProfileReadSchema.array())
}

export function saveProfilesToStorage(data: LocalMediaProfileRead[] | undefined) {
  try {
    if (!data) {
      localStorage.removeItem(KEY_PROFILES)
    } else {
      localStorage.setItem(KEY_PROFILES, JSON.stringify(data))
    }
  } catch {
    // ignore
  }
}
