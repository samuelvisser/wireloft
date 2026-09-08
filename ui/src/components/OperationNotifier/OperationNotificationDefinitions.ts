import {PUBLISH_STATUS_LABELS} from '../../types/episode'
import {type TaskOperationRead} from '../../types/schemas/operation'

type OperationMessageResolver = (operation: TaskOperationRead) => string

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

export const operationNotificationDefinitions = {
  'show.index': {
    label: 'Show indexing',
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
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      const count = resultNumber(operation, 'episodes_found') ?? 0
      return `Sync finished for ${showTitle}: ${count} new ${plural(count, 'episode')} found`
    },
  },
  'show.refresh_metadata': {
    label: 'Metadata refresh',
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
    success: (operation) => {
      const episodeTitle = contextString(operation, 'episode_title') || operation.title
      return `Metadata refresh completed for ${episodeTitle}`
    },
  },
  'episode.early_delete': {
    label: 'Early delete',
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
    success: (operation) => {
      const showTitle = contextString(operation, 'show_title') || operation.title
      return fileRenameSuccessMessage(operation, showTitle)
    },
  },
  'local_media_profile.rename_files': {
    label: 'File Rename',
    success: (operation) => {
      const profileName = contextString(operation, 'local_media_profile_name') || operation.title
      return fileRenameSuccessMessage(operation, profileName)
    },
  },
  'show.redownload_episodes': {
    label: 'Re-download',
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
  },
  'media.download': {
    label: 'Download',
    success: (operation) => operation.result?.summary || `Downloaded ${operation.title}`,
  },
} satisfies OperationNotificationDefinitions
