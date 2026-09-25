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
  kind: string
  resourceType: string
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

function completedCount(operation: TaskOperationRead): number {
  return resultNumber(operation, 'completed') ?? operation.progressCurrent
}

function httpErrorMessage(error: string | null | undefined): string | undefined {
  if (!error) return undefined

  const match = error.match(/^HTTP error \d+:\s*([\s\S]+)$/)
  if (!match) return undefined

  try {
    const parsed = JSON.parse(match[1])
    if (parsed && typeof parsed === 'object' && typeof parsed.error === 'string' && parsed.error.trim()) {
      return parsed.error
    }
  } catch {
    // Fall back to the ordinary operation failure message for non-JSON HTTP errors.
  }

  return undefined
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

function invalidateShowDownloadDeletion(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateShowFiles(queryClient, operation, invalidations)
  invalidations.push(queryClient.invalidateQueries({queryKey: ['downloadProfilesView']}))
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

function invalidateMediaDownloadCollection(
  queryClient: QueryClient,
  _operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
    queryClient.invalidateQueries({queryKey: ['episodeDownloads']}),
    queryClient.invalidateQueries({queryKey: ['movieDownloads']}),
    queryClient.invalidateQueries({queryKey: ['movies']}),
  )
}

export const frontendOperationDefinitions = {
  'show.index': {
    kind: 'show.index',
    resourceType: 'show',
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
    kind: 'show.sync',
    resourceType: 'show',
    label: 'Sync',
    invalidate: invalidateShow,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const count = resultNumber(operation, 'episodes_found') ?? 0
      return `Sync finished for ${showTitle}: ${count} new ${plural(count, 'episode')} found`
    },
  },
  'show.refresh_metadata': {
    kind: 'show.refresh_metadata',
    resourceType: 'show',
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
    kind: 'episode.refresh_metadata',
    resourceType: 'episode',
    label: 'Metadata refresh',
    invalidate: invalidateEpisode,
    success: (operation) => {
      const episodeTitle = contextString(operation, 'episode_title') || operation.title
      return `Metadata refresh completed for ${episodeTitle}`
    },
  },
  'episode.early_delete': {
    kind: 'episode.early_delete',
    resourceType: 'episode',
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
    kind: 'show.rename_files',
    resourceType: 'show',
    label: 'File Rename',
    invalidate: invalidateShowFiles,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      return fileRenameSuccessMessage(operation, showTitle)
    },
  },
  'local_media_profile.manage_custom_indexes': {
    kind: 'local_media_profile.manage_custom_indexes',
    resourceType: 'local_media_profile',
    label: 'Custom indexing',
    invalidate: invalidateLocalMediaProfileFiles,
    success: (operation) => {
      const profileName = contextString(operation, 'local_media_profile_name') || operation.title
      return `Custom indexing updated for ${profileName}`
    },
  },
  'local_media_profile.rename_files': {
    kind: 'local_media_profile.rename_files',
    resourceType: 'local_media_profile',
    label: 'File Rename',
    invalidate: invalidateLocalMediaProfileFiles,
    success: (operation) => {
      const profileName = contextString(operation, 'local_media_profile_name') || operation.title
      return fileRenameSuccessMessage(operation, profileName)
    },
  },
  'show.delete_downloads': {
    kind: 'show.delete_downloads',
    resourceType: 'show',
    label: 'Delete downloads',
    invalidate: invalidateShowDownloadDeletion,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const files = resultNumber(operation, 'episode_files') ?? 0
      const profiles = resultNumber(operation, 'local_media_profiles')
      const disabledProfiles = resultNumber(operation, 'download_profiles_disabled') ?? 0
      const profileDetail = profiles === undefined
        ? ''
        : ` using ${profiles} ${plural(profiles, 'Local Media Profile')}`
      const disabledDetail = disabledProfiles > 0
        ? `; ${disabledProfiles} ${plural(disabledProfiles, 'Download Profile')} disabled`
        : ''
      return `Deleted downloads for ${showTitle}: ${files} episode ${plural(files, 'file')} deleted${profileDetail}${disabledDetail}`
    },
  },
  'show.redownload_episodes': {
    kind: 'show.redownload_episodes',
    resourceType: 'show',
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
    kind: 'movie.refresh_extras',
    resourceType: 'movie',
    label: 'Movie extra refresh',
    invalidate: invalidateMovie,
  },
  'media_download.bulk_retry': {
    kind: 'media_download.bulk_retry',
    resourceType: 'media_download',
    label: 'Retry downloads',
    invalidate: invalidateMediaDownloadCollection,
    success: (operation) => {
      const count = operation.progressTotal
      return `${count} ${plural(count, 'download')} queued for retry`
    },
    partial: (operation) => (
      `${completedCount(operation)} of ${operation.progressTotal} downloads queued for retry`
    ),
    canceled: (operation) => (
      `Retry all canceled after ${completedCount(operation)} of ${operation.progressTotal} downloads`
    ),
  },
  'media_download.bulk_cancel': {
    kind: 'media_download.bulk_cancel',
    resourceType: 'media_download',
    label: 'Cancel downloads',
    invalidate: invalidateMediaDownloadCollection,
    success: (operation) => {
      const count = operation.progressTotal
      return `Canceled ${count} ${plural(count, 'download')}`
    },
    partial: (operation) => (
      `Canceled ${completedCount(operation)} of ${operation.progressTotal} downloads`
    ),
    canceled: (operation) => (
      `Cancel all stopped after ${completedCount(operation)} of ${operation.progressTotal} downloads`
    ),
  },
  'media_download.bulk_delete': {
    kind: 'media_download.bulk_delete',
    resourceType: 'media_download',
    label: 'Delete downloads',
    invalidate: invalidateMediaDownloadCollection,
    success: (operation) => {
      const count = operation.progressTotal
      return `Deleted ${count} download ${plural(count, 'record')}`
    },
    partial: (operation) => (
      `Deleted ${completedCount(operation)} of ${operation.progressTotal} download records`
    ),
    canceled: (operation) => (
      `Delete all stopped after ${completedCount(operation)} of ${operation.progressTotal} download records`
    ),
  },
  'media.download': {
    kind: 'media.download',
    resourceType: 'media_download',
    label: 'Download',
    invalidate: invalidateMediaDownload,
    success: (operation) => operation.result?.summary || `Downloaded ${operation.title}`,
    failed: (operation) => httpErrorMessage(operation.error)
      ?? `Download failed for ${operation.title}${operation.error ? `: ${operation.error}` : ''}`,
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
