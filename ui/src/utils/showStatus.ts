import type { EpisodeStatus } from '../domain/show'

export function statusIcon(status: EpisodeStatus) {
  switch (status) {
    case 'downloaded':
      return ['fas', 'circle-check'] as const
    case 'downloading':
      return ['fas', 'arrow-down'] as const
    case 'processing':
      return ['fas', 'spinner'] as const
    case 'error':
      return ['fas', 'circle-exclamation'] as const
  }
}

export function statusLabel(status: EpisodeStatus) {
  switch (status) {
    case 'downloaded':
      return 'Downloaded'
    case 'downloading':
      return 'Downloading'
    case 'processing':
      return 'Waiting for processing'
    case 'error':
      return 'Error'
  }
}