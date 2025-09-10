// Domain types: shared everywhere
export type EpisodeStatus = 'scheduled' | 'live' | 'dw_processing' | 'published' | 'downloaded' | 'downloading' | 'local_processing' | 'error'

export type Episode = {
  id: number
  slug: string
  title: string
  index: number
  cover?: string
  unified_status: EpisodeStatus
}

export type Show = {
  id: number
  slug: string
  author: string
  title: string
  years?: string
}
