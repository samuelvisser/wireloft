// Types used by the Add Show wizard so each step has a clear, API-ready model
// These mirror the backend Pydantic request models. The backend accepts camelCase input
// and converts it to snake_case.

// 1) Show (matches backend ShowAPICreate)
export type AddShowShow = {
  // core
  title: string
  description?: string | null
  url: string
  authorName: string | null
  // optional media paths (URLs accepted)
  authorHeadshotPath?: string | null
  backgroundImagePath?: string | null
  logoImagePath?: string | null
  thumbnailLandscapePath?: string | null
  thumbnailPortraitPath?: string | null
  thumbnailSquarePath?: string | null

  // required create-time fields
  dwId: string
  slug: string
  type: 'podcast' | 'series'
  episodeIdentifier: 'date_based' | 'numbered'
  authorSlug: string | null
}

// 2) Media Profile upsert for the bundle
export type MediaProfileCreateNew = {
  op: 'create_new'
  name: string
  outputTemplate: string | null
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only' | null
  downloadSeriesImages: boolean
}

export type MediaProfileUpdateBySlug = {
  op: 'update_by_slug'
  slug: string
  name: string
  outputTemplate: string | null
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only' | null
  downloadSeriesImages: boolean
}

export type AddShowMediaProfileUpsert = MediaProfileCreateNew | MediaProfileUpdateBySlug

// 3) Download Profile (matches backend DownloadProfileAPICreate)
export type AddShowDownloadProfile = {
  showId: number
  mediaProfileId: number
  enableProfile: boolean
  downloadWithCountdown: boolean
  redownloadFinal: boolean
  downloadDaysInPast: number
  deleteOlderEpisodes: boolean
}

// Final bundle payload (matches backend ShowAPICreateBundle)
export type AddShowBundle = {
  show: AddShowShow
  downloadProfile: AddShowDownloadProfile
  mediaProfile: AddShowMediaProfileUpsert
}
