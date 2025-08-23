// Simple localStorage persistence for React Query data we care about
// Focuses on 'shows' and 'mediaProfiles' to prevent flicker on reload

const STORAGE_PREFIX = 'wl_rq_v1:'
const KEY_SHOWS = STORAGE_PREFIX + 'shows'
const KEY_PROFILES = STORAGE_PREFIX + 'mediaProfiles'

function safeParse<T>(raw: string | null): T | undefined {
  if (!raw) return undefined
  try {
    return JSON.parse(raw) as T
  } catch {
    return undefined
  }
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

export function loadProfilesFromStorage(): any[] | undefined {
  return safeParse<any[]>(localStorage.getItem(KEY_PROFILES))
}

export function saveProfilesToStorage(data: any[] | undefined) {
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
