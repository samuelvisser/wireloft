// Simple localStorage persistence for React Query data we care about
// Focuses on shows, show episodes, and local media profiles to prevent flicker on reload

import {LocalMediaProfileRead} from "../types/schemas/local_media_profile";
import {EpisodeRead} from "../types/schemas/episode";

const STORAGE_PREFIX = 'wl_rq_v1:'
const KEY_SHOWS = STORAGE_PREFIX + 'shows'
const KEY_PROFILES = STORAGE_PREFIX + 'localMediaProfiles'
const KEY_EPISODES_PREFIX = STORAGE_PREFIX + 'episodes:'

function safeParse<T>(raw: string | null): T | undefined {
  if (!raw) return undefined
  try {
    return JSON.parse(raw) as T
  } catch {
    return undefined
  }
}

function episodesStorageKey(showSlug: string) {
  return KEY_EPISODES_PREFIX + encodeURIComponent(showSlug)
}

export function loadShowsFromStorage(): any[] | undefined {
  return safeParse<any[]>(localStorage.getItem(KEY_SHOWS))
}

export function saveShowsToStorage(data: any[] | undefined) {
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
  return safeParse<EpisodeRead[]>(localStorage.getItem(episodesStorageKey(showSlug)))
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

export function loadProfilesFromStorage(): any[] | undefined {
  return safeParse<any[]>(localStorage.getItem(KEY_PROFILES))
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
