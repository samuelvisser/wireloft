// Domain types: shared everywhere
export type EpisodeStatus = 'downloaded' | 'downloading' | 'processing' | 'error'

export type Episode = {
  id: number
  slug: string
  title: string
  index: number
  cover?: string
  status: EpisodeStatus
}

export type Show = {
  id: number
  slug: string
  author: string
  title: string
  years?: string
}
