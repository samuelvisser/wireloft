// Domain types: shared everywhere
export type EpisodeStatus =
    'scheduled' |
    'delayed' |
    'live' |
    'dw_processing' |
    'published_with_countdown' |
    'published_final' |
    'downloaded' |
    'downloading' |
    'redownloaded' |
    'local_processing' |
    'error'

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
