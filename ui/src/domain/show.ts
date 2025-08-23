// Domain types: shared everywhere
export type EpisodeStatus = 'downloaded' | 'downloading' | 'processing' | 'error'

export type Episode = {
  id: string
  title: string
  index: number
  cover?: string
  status: EpisodeStatus
}

export type Show = {
  id: string
  author: string
  title: string
  years?: string
  episodes: Episode[]
}
