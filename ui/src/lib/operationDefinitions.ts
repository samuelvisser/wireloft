import {type QueryClient} from '@tanstack/react-query'

import {PUBLISH_STATUS_LABELS} from '../types/episode'
import {type TaskOperationRead} from '../types/schemas/operation'

export type OperationMessageResolver = (operation: TaskOperationRead) => string

export type OperationNotificationDefinition = {
  label: string
  success?: OperationMessageResolver
  partial?: OperationMessageResolver
  canceled?: OperationMessageResolver
  failed?: OperationMessageResolver
}

export type OperationNotificationDefinitions = Readonly<
  Record<string, OperationNotificationDefinition>
>

type InvalidationCollector = Promise<unknown>[]
type OperationInvalidation = (
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) => void

export type FrontendOperationDefinition = OperationNotificationDefinition & {
  invalidate?: OperationInvalidation
}

function contextString(operation: TaskOperationRead, key: string): string | undefined {
  const value = operation.context?.[key]
  return typeof value === 'string' && value ? value : undefined
}

function resultString(operation: TaskOperationRead, key: string): string | undefined {
  const value = operation.result?.data?.[key]
  return typeof value === 'string' && value ? value : undefined
}

function resultNumber(operation: TaskOperationRead, key: string): number | undefined {
  const value = operation.result?.data?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function plural(value: number, singular: string, pluralForm = `${singular}s`) {
  return value === 1 ? singular : pluralForm
}

function fileRenameSuccessMessage(operation: TaskOperationRead, title: string): string {
  const renamed = (resultNumber(operation, 'files_renamed') ?? 0)
    + (resultNumber(operation, 'files_recovered') ?? 0)
  const unchanged = resultNumber(operation, 'files_unchanged') ?? 0
  const considered = resultNumber(operation, 'files_considered') ?? (renamed + unchanged)
  if (considered === 0) return `No existing files needed renaming for ${title}`
  const unchangedDetail = unchanged > 0 ? `; ${unchanged} already matched` : ''
  return `File Rename finished for ${title}: ${renamed} ${plural(renamed, 'file')} renamed${unchangedDetail}`
}

function invalidateShow(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  const showSlug = contextString(operation, 'show_slug')
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

function invalidateShowFiles(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateShow(queryClient, operation, invalidations)
  invalidations.push(queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}))
}

function invalidateEpisode(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  const episodeSlug = contextString(operation, 'episode_slug')
  const resultEpisodeSlug = resultString(operation, 'episode_slug')
  const showSlug = contextString(operation, 'show_slug')
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

function invalidateMovie(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  const movieSlug = contextString(operation, 'movie_slug')
  invalidations.push(queryClient.invalidateQueries({queryKey: ['movies']}))
  if (movieSlug) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['dailywireMovie', movieSlug]}),
    )
  }
}

function invalidateLocalMediaProfileFiles(
  queryClient: QueryClient,
  _operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
    queryClient.invalidateQueries({queryKey: ['localMediaProfiles']}),
    queryClient.invalidateQueries({queryKey: ['localMediaProfile']}),
  )
}

function invalidateMediaDownload(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  const episodeSlug = contextString(operation, 'episode_slug')
  const showSlug = contextString(operation, 'show_slug')
  const movieSlug = contextString(operation, 'movie_slug')

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

export const frontendOperationDefinitions = {
  'show.index': {
    label: 'Show indexing',
    invalidate: invalidateShow,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const count = resultNumber(operation, 'episodes_found')
      return count === undefined
        ? `Indexing finished for ${showTitle}`
        : `Indexed ${showTitle}: ${count} ${plural(count, 'episode')} found`
    },
  },
  'show.sync': {
    label: 'Sync',
    invalidate: invalidateShow,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const count = resultNumber(operation, 'episodes_found') ?? 0
      return `Sync finished for ${showTitle}: ${count} new ${plural(count, 'episode')} found`
    },
  },
  'show.refresh_metadata': {
    label: 'Metadata refresh',
    invalidate: invalidateShow,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const count = operation.progressTotal
      return count === 0
        ? `No episodes to refresh in ${showTitle}`
        : `Metadata refresh completed for ${count} ${plural(count, 'episode')} in ${showTitle}`
    },
  },
  'episode.refresh_metadata': {
    label: 'Metadata refresh',
    invalidate: invalidateEpisode,
    success: (operation) => {
      const episodeTitle = contextString(operation, 'episode_title') || operation.title
      return `Metadata refresh completed for ${episodeTitle}`
    },
  },
  'episode.early_delete': {
    label: 'Early delete',
    invalidate: invalidateEpisode,
    success: (operation) => {
      const episodeTitle = contextString(operation, 'episode_title') || operation.title
      const outcome = resultString(operation, 'outcome')
      if (outcome === 'recovered' || outcome === 'replaced') {
        const publishStatus = resultString(operation, 'publish_status')
        const statusLabel = publishStatus
          ? (PUBLISH_STATUS_LABELS[publishStatus] ?? publishStatus)
          : undefined
        return statusLabel
          ? `Recovered ${episodeTitle} to ${statusLabel} state`
          : `Recovered ${episodeTitle}`
      }
      if (outcome === 'deleted') return `Deleted ${episodeTitle}`
      if (outcome === 'retained') return `${episodeTitle} remains in No usable media state`
      if (outcome === 'unverified') return `Could not verify ${episodeTitle}; it was not deleted`
      if (outcome === 'already_resolved') {
        return `${episodeTitle} no longer needs No usable media verification`
      }
      return `Early delete completed for ${episodeTitle}`
    },
  },
  'show.rename_files': {
    label: 'File Rename',
    invalidate: invalidateShowFiles,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      return fileRenameSuccessMessage(operation, showTitle)
    },
  },
  'local_media_profile.rename_files': {
    label: 'File Rename',
    invalidate: invalidateLocalMediaProfileFiles,
    success: (operation) => {
      const profileName = contextString(operation, 'local_media_profile_name') || operation.title
      return fileRenameSuccessMessage(operation, profileName)
    },
  },
  'show.delete_downloads': {
    label: 'Delete downloads',
    invalidate: invalidateShowFiles,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const files = resultNumber(operation, 'episode_files') ?? 0
      const profiles = resultNumber(operation, 'local_media_profiles')
      const profileDetail = profiles === undefined
        ? ''
        : ` using ${profiles} ${plural(profiles, 'Local Media Profile')}`
      return `Deleted downloads for ${showTitle}: ${files} episode ${plural(files, 'file')} deleted${profileDetail}`
    },
  },
  'show.redownload_episodes': {
    label: 'Re-download',
    invalidate: invalidateShowFiles,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const files = resultNumber(operation, 'episode_files') ?? 0
      const profiles = resultNumber(operation, 'local_media_profiles')
      const profileDetail = profiles === undefined
        ? ''
        : ` using ${profiles} ${plural(profiles, 'Local Media Profile')}`
      return `Re-download finished for ${showTitle}: ${files} episode ${plural(files, 'file')} re-downloaded${profileDetail}`
    },
  },
  'movie.refresh_extras': {
    label: 'Movie extra refresh',
    invalidate: invalidateMovie,
  },
  'media.download': {
    label: 'Download',
    invalidate: invalidateMediaDownload,
    success: (operation) => operation.result?.summary || `Downloaded ${operation.title}`,
  },
} satisfies Readonly<Record<string, FrontendOperationDefinition>>

export const operationNotificationDefinitions: OperationNotificationDefinitions =
  frontendOperationDefinitions

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
  const invalidations: InvalidationCollector = [
    queryClient.invalidateQueries({
      predicate: (query) => taskLedgerQueryMatchesOperation(query.queryKey, operation),
    }),
  ]

  frontendOperationDefinitions[
    operation.kind as keyof typeof frontendOperationDefinitions
  ]?.invalidate?.(queryClient, operation, invalidations)

  await Promise.all(invalidations)
}
