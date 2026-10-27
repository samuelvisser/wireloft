import {type QueryClient} from '@tanstack/react-query'

import {PUBLISH_STATUS_LABELS} from '../types/episode'
import {type TaskOperationRead} from '../types/schemas/operation'
import {removeEpisodePreviewFromStorage, removeSeasonsFromStorage} from './cache'
import {episodeQueryKeys} from './showQueryOptions'

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

function contextNumber(operation: TaskOperationRead, key: string): number | undefined {
  const value = operation.context?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
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

function invalidateShowEpisodeQueries(
  queryClient: QueryClient,
  showSlug: string,
  invalidations: InvalidationCollector,
) {
  removeEpisodePreviewFromStorage(showSlug)
  invalidations.push(
    queryClient.invalidateQueries({queryKey: episodeQueryKeys.forShow(showSlug)}),
  )
}

function invalidateShowEpisodeData(
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
    invalidations.push(queryClient.invalidateQueries({queryKey: ['show', showSlug]}))
    invalidateShowEpisodeQueries(queryClient, showSlug, invalidations)
  }
}

function invalidateShowStructure(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateShowEpisodeData(queryClient, operation, invalidations)
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['recentlyIndexedEpisodes']}),
  )
  const showSlug = contextString(operation, 'show_slug')
  if (!showSlug) return

  removeSeasonsFromStorage(showSlug)
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['seasons', showSlug]}),
  )
}

function invalidateShowFiles(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  const showSlug = contextString(operation, 'show_slug')
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
  )
  if (showSlug) {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['showDownloads', showSlug]}))
  }
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
    invalidateShowEpisodeQueries(queryClient, showSlug, invalidations)
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

function invalidateMovieFiles(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateMovie(queryClient, operation, invalidations)
  const movieSlug = contextString(operation, 'movie_slug')
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
  )
  if (movieSlug) {
    invalidations.push(queryClient.invalidateQueries({queryKey: ['movieDownloads', movieSlug]}))
  }
}

function invalidateLocalMediaProfileFiles(
  queryClient: QueryClient,
  _operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
    queryClient.invalidateQueries({queryKey: ['episodeDownloads']}),
    queryClient.invalidateQueries({queryKey: ['movieDownloads']}),
    queryClient.invalidateQueries({queryKey: ['showDownloads']}),
    queryClient.invalidateQueries({queryKey: ['localMediaProfiles']}),
    queryClient.invalidateQueries({queryKey: ['localMediaProfile']}),
    queryClient.invalidateQueries({queryKey: ['localMediaProfileView']}),
  )
}

function invalidateLocalMediaProfileDownloadDeletion(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateLocalMediaProfileFiles(queryClient, operation, invalidations)
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['downloadProfilesView']}),
    queryClient.invalidateQueries({queryKey: ['podcastDownloadProfiles']}),
    queryClient.invalidateQueries({queryKey: ['seriesDownloadProfiles']}),
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

  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
  )
  if (operation.resourceId != null) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['mediaDownloadHistory', operation.resourceId]}),
    )
  }
  if (episodeSlug) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['episodeDownloads', episodeSlug]}),
    )
  }
  if (showSlug) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['showDownloads', showSlug]}),
    )
  }
  if (movieSlug) {
    invalidations.push(
      queryClient.invalidateQueries({queryKey: ['movieDownloads', movieSlug]}),
      queryClient.invalidateQueries({queryKey: ['movies']}),
    )
  }
}

function invalidateMediaDownloadCollection(
  queryClient: QueryClient,
  _operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
    queryClient.invalidateQueries({queryKey: ['episodeDownloads']}),
    queryClient.invalidateQueries({queryKey: ['movieDownloads']}),
    queryClient.invalidateQueries({queryKey: ['showDownloads']}),
    queryClient.invalidateQueries({queryKey: ['movies']}),
  )
}

function invalidateTaskLedgerDefinition(
  queryClient: QueryClient,
  definitionKey: string,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['taskLedger', definitionKey]}),
    queryClient.invalidateQueries({queryKey: ['taskLedger', 'list', definitionKey]}),
  )
}

function invalidateEpisodeCronJob(
  queryClient: QueryClient,
  _operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['shows']}),
    queryClient.invalidateQueries({queryKey: ['showsView']}),
    queryClient.invalidateQueries({queryKey: ['episodes']}),
    queryClient.invalidateQueries({queryKey: ['recentlyIndexedEpisodes']}),
  )
}

function invalidateEpisodeAndDownloadCronJob(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateEpisodeCronJob(queryClient, operation, invalidations)
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
  )
}

function invalidateDownloadCronJob(
  queryClient: QueryClient,
  _operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidations.push(
    queryClient.invalidateQueries({queryKey: ['mediaDownloads']}),
    queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
  )
}

function invalidateFindEpisodesCron(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateEpisodeCronJob(queryClient, operation, invalidations)
  invalidateTaskLedgerDefinition(queryClient, 'fetch_new_episodes', invalidations)
}

function invalidatePendingEpisodeCron(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateEpisodeAndDownloadCronJob(queryClient, operation, invalidations)
  invalidateTaskLedgerDefinition(queryClient, 'monitor_pending_episode', invalidations)
}

function invalidateNoUsableMediaCron(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateEpisodeAndDownloadCronJob(queryClient, operation, invalidations)
  invalidateTaskLedgerDefinition(queryClient, 'monitor_no_usable_media_episode', invalidations)
}

function invalidateVerifyDownloadsCron(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateDownloadCronJob(queryClient, operation, invalidations)
  invalidateTaskLedgerDefinition(queryClient, 'download_profile_worker', invalidations)
}

function invalidateFileWatcherCron(
  queryClient: QueryClient,
  operation: TaskOperationRead,
  invalidations: InvalidationCollector,
) {
  invalidateDownloadCronJob(queryClient, operation, invalidations)
  invalidateTaskLedgerDefinition(queryClient, 'file_watcher', invalidations)
}

export const frontendOperationDefinitions = {
  'system.cron.find_episodes': {
    kind: 'system.cron.find_episodes',
    resourceType: 'system',
    label: 'Find new episodes',
    invalidate: invalidateFindEpisodesCron,
  },
  'system.cron.monitor_pending_episodes': {
    kind: 'system.cron.monitor_pending_episodes',
    resourceType: 'system',
    label: 'Monitor pending episodes',
    invalidate: invalidatePendingEpisodeCron,
  },
  'system.cron.monitor_no_usable_media': {
    kind: 'system.cron.monitor_no_usable_media',
    resourceType: 'system',
    label: 'Monitor episodes without usable media',
    invalidate: invalidateNoUsableMediaCron,
  },
  'system.cron.verify_downloads': {
    kind: 'system.cron.verify_downloads',
    resourceType: 'system',
    label: 'Verify downloads',
    invalidate: invalidateVerifyDownloadsCron,
  },
  'system.cron.file_watcher': {
    kind: 'system.cron.file_watcher',
    resourceType: 'system',
    label: 'File watcher',
    invalidate: invalidateFileWatcherCron,
  },
  'show.index': {
    kind: 'show.index',
    resourceType: 'show',
    label: 'Show indexing',
    invalidate: invalidateShowStructure,
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
    invalidate: invalidateShowStructure,
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
    invalidate: invalidateShowEpisodeData,
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
  'local_media_profile.redownload_media': {
    kind: 'local_media_profile.redownload_media',
    resourceType: 'local_media_profile',
    label: 'Re-download media',
    invalidate: invalidateLocalMediaProfileFiles,
    success: (operation) => {
      const profileName = contextString(operation, 'local_media_profile_name') || operation.title
      const count = resultNumber(operation, 'downloads_completed')
        ?? resultNumber(operation, 'completed')
        ?? contextNumber(operation, 'downloads_requested')
        ?? 0
      return `Re-download finished for ${profileName}: ${count} ${plural(count, 'file')} re-downloaded`
    },
  },
  'local_media_profile.delete_downloads': {
    kind: 'local_media_profile.delete_downloads',
    resourceType: 'local_media_profile',
    label: 'Delete downloads',
    invalidate: invalidateLocalMediaProfileDownloadDeletion,
    success: (operation) => {
      const profileName = contextString(operation, 'local_media_profile_name') || operation.title
      const files = resultNumber(operation, 'files_deleted') ?? operation.progressTotal
      const disabledProfiles = contextNumber(operation, 'download_profiles_disabled') ?? 0
      const disabledDetail = disabledProfiles > 0
        ? `; ${disabledProfiles} ${plural(disabledProfiles, 'Download Profile')} disabled`
        : ''
      return `Deleted downloads for ${profileName}: ${files} ${plural(files, 'file')} removed${disabledDetail}`
    },
  },
  'show.delete_downloads': {
    kind: 'show.delete_downloads',
    resourceType: 'show',
    label: 'Bulk delete downloads',
    invalidate: invalidateShowDownloadDeletion,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const files = resultNumber(operation, 'episode_files')
        ?? resultNumber(operation, 'completed')
        ?? 0
      const profiles = resultNumber(operation, 'local_media_profiles')
        ?? contextNumber(operation, 'local_media_profiles_requested')
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
  'show.download_all': {
    kind: 'show.download_all',
    resourceType: 'show',
    label: 'Bulk download',
    invalidate: invalidateShowFiles,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const completed = resultNumber(operation, 'downloads_completed')
        ?? resultNumber(operation, 'completed')
        ?? contextNumber(operation, 'downloads_requested')
        ?? 0
      return `Bulk download finished for ${showTitle}: ${completed} ${plural(completed, 'episode')} downloaded`
    },
  },
  'show.redownload_episodes': {
    kind: 'show.redownload_episodes',
    resourceType: 'show',
    label: 'Bulk delete and re-download',
    invalidate: invalidateShowFiles,
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const files = resultNumber(operation, 'episode_files')
        ?? resultNumber(operation, 'completed')
        ?? contextNumber(operation, 'downloads_requested')
        ?? 0
      const profiles = resultNumber(operation, 'local_media_profiles')
        ?? contextNumber(operation, 'local_media_profiles_requested')
      const profileDetail = profiles === undefined
        ? ''
        : ` using ${profiles} ${plural(profiles, 'Local Media Profile')}`
      return `Bulk delete and re-download finished for ${showTitle}: ${files} episode ${plural(files, 'file')} re-downloaded${profileDetail}`
    },
  },
  'movie.refresh_extras': {
    kind: 'movie.refresh_extras',
    resourceType: 'movie',
    label: 'Movie extra refresh',
    invalidate: invalidateMovie,
  },
  'movie.redownload_media': {
    kind: 'movie.redownload_media',
    resourceType: 'movie',
    label: 'Re-download media',
    invalidate: invalidateMovieFiles,
    success: (operation) => {
      const movieTitle = contextString(operation, 'movie_title') || operation.title
      const count = resultNumber(operation, 'downloads_completed')
        ?? resultNumber(operation, 'completed')
        ?? contextNumber(operation, 'downloads_requested')
        ?? 0
      return `Re-download finished for ${movieTitle}: ${count} ${plural(count, 'file')} re-downloaded`
    },
  },
  'media_download.bulk_retry': {
    kind: 'media_download.bulk_retry',
    resourceType: 'media_download',
    label: 'Retry downloads',
    invalidate: invalidateMediaDownloadCollection,
    success: (operation) => {
      const count = resultNumber(operation, 'downloads_completed')
        ?? resultNumber(operation, 'completed')
        ?? contextNumber(operation, 'downloads_requested')
        ?? 0
      return `Retry finished for ${count} ${plural(count, 'download')}`
    },
    canceled: (operation) => {
      const count = contextNumber(operation, 'downloads_requested') ?? 0
      return `Retry all canceled before all ${count} ${plural(count, 'download')} finished`
    },
    failed: (operation) => operation.error
      ? `Retry all failed: ${operation.error}`
      : 'Retry all failed',
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
  'media_download.bulk_delete_unavailable': {
    kind: 'media_download.bulk_delete_unavailable',
    resourceType: 'media_download',
    label: 'Delete unavailable download records',
    invalidate: invalidateMediaDownloadCollection,
    success: (operation) => {
      const count = resultNumber(operation, 'downloads_deleted') ?? operation.progressTotal
      return `Deleted ${count} ${plural(count, 'download record')}`
    },
    partial: (operation) => {
      const count = resultNumber(operation, 'downloads_deleted') ?? completedCount(operation)
      return `Deleted ${count} of ${operation.progressTotal} unavailable download records`
    },
    canceled: (operation) => {
      const count = resultNumber(operation, 'downloads_deleted') ?? completedCount(operation)
      return `Delete unavailable stopped after ${count} of ${operation.progressTotal} records`
    },
    failed: (operation) => operation.error
      ? `Delete unavailable failed: ${operation.error}`
      : 'Delete unavailable failed',
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

  const lazyCollection = queryKey[1] === 'list'
  const resourceType = lazyCollection ? queryKey[3] : queryKey[2]
  if (
    resourceType !== undefined
    && resourceType !== null
    && resourceType !== operation.resourceType
  ) {
    return false
  }

  const resourceFilter = lazyCollection ? queryKey[4] : queryKey[3]
  if (resourceFilter === undefined || resourceFilter === null || operation.resourceId == null) {
    return true
  }
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
