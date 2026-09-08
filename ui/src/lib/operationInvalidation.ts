import {type QueryClient} from '@tanstack/react-query'
import {type TaskOperationRead} from '../types/schemas/operation'

function contextString(operation: TaskOperationRead, key: string): string | undefined {
  const value = operation.context?.[key]
  return typeof value === 'string' && value ? value : undefined
}

function resultString(operation: TaskOperationRead, key: string): string | undefined {
  const value = operation.result?.data?.[key]
  return typeof value === 'string' && value ? value : undefined
}

function taskLedgerQueryMatchesOperation(
  queryKey: readonly unknown[],
  operation: TaskOperationRead,
): boolean {
  if (queryKey[0] !== 'taskLedger') return false

  const resourceType = queryKey[2]
  if (resourceType !== undefined && resourceType !== operation.resourceType) return false

  const resourceFilter = queryKey[3]
  if (resourceFilter === undefined || operation.resourceId == null) return true
  if (typeof resourceFilter === 'number') return resourceFilter === operation.resourceId
  return Array.isArray(resourceFilter) && resourceFilter.includes(operation.resourceId)
}

export async function invalidateForOperation(
  queryClient: QueryClient,
  operation: TaskOperationRead,
) {
  const showSlug = contextString(operation, 'show_slug')
  const episodeSlug = contextString(operation, 'episode_slug')
  const resultEpisodeSlug = resultString(operation, 'episode_slug')
  const movieSlug = contextString(operation, 'movie_slug')
  const invalidations: Promise<unknown>[] = [
    queryClient.invalidateQueries({
      predicate: (query) => taskLedgerQueryMatchesOperation(query.queryKey, operation),
    }),
  ]

  if (operation.kind.startsWith('show.')) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['shows']}),
      queryClient.invalidateQueries({queryKey: ['showsView']}),
    )
    if (showSlug) {
      invalidations.push(
        queryClient.invalidateQueries({queryKey: ['show', showSlug]}),
        queryClient.invalidateQueries({queryKey: ['episodes', showSlug]}),
      )
    }
  }

  if (
    operation.kind === 'show.redownload_episodes'
    || operation.kind === 'show.rename_files'
    || operation.kind === 'local_media_profile.rename_files'
  ) {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}))
  }

  if (operation.kind === 'local_media_profile.rename_files') {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['localMediaProfiles']}),
      queryClient.invalidateQueries({queryKey: ['localMediaProfile']}),
    )
  }

  if (operation.kind.startsWith('episode.')) {
    if (episodeSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episode', episodeSlug]}))
    }
    if (resultEpisodeSlug && resultEpisodeSlug !== episodeSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episode', resultEpisodeSlug]}))
    }
    if (showSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episodes', showSlug]}))
    }
  }

  if (operation.kind.startsWith('movie.')) {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['movies']}))
    if (movieSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['dailywireMovie', movieSlug]}))
    }
  }

  if (operation.kind === 'media.download') {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}))
    if (episodeSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episode', episodeSlug]}))
    }
    if (showSlug) {
      invalidations.push(queryClient.invalidateQueries({queryKey: ['episodes', showSlug]}))
    }
    if (movieSlug) {
      invalidations.push(
        queryClient.invalidateQueries({queryKey: ['movies']}),
        queryClient.invalidateQueries({queryKey: ['dailywireMovie', movieSlug]}),
      )
    }
  }

  await Promise.all(invalidations)
}
