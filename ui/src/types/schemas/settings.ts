import {z} from 'zod'
import {createServerErrorMapper} from '../../utils/serverMessageMap'


const CryptoFileSettingsSchema = z.object({
    secretKeyFile: z.string().nullable(),
    defaultSecretFile: z.string(),
})

const SessionSettingsSchema = z.object({
    ttlSeconds: z.number(),
})

const DailyWireAPISettingsSchema = z.object({
    middlewareApi: z.string(),
    streamApi: z.string(),
})

const MovieMetadataSettingsSchema = z.object({
    // The API never returns the stored secret. This is a write-only replacement value.
    tmdbReadAccessToken: z.string(),
    tmdbReadAccessTokenConfigured: z.boolean(),
    tmdbApiBaseUrl: z.string(),
    language: z.string(),
    requestTimeoutSeconds: z.number(),
    maxRetries: z.number(),
})

const OAuthSettingsSchema = z.object({
    issuer: z.string(),
    audience: z.string(),
    clientId: z.string(),
    scope: z.string(),
})

const TimeoutSettingsSchema = z.object({
    minFastRequestMs: z.number(),
    maxFastRequests: z.number(),
    minSlowRequestMs: z.number(),
})

const SchedulerSettingsSchema = z.object({
    enabled: z.boolean(),
    maxWorkers: z.number(),
    defaultMaxRetries: z.number(),
    retryBackoffSeconds: z.number(),
})

const TrackNewEpisodeScheduleSchema = z.object({
    findEpisodesCron: z.string(),
    monitorEpisodeCron: z.string(),
    checkNoShowTodayCron: z.string(),
    metadataRefreshIntervals: z.string(),
})

const EpisodeStatusTimingSchema = z.object({
    publishedCountdownAfterMinutes: z.number(),
    publishedFinalAfterMinutes: z.number(),
})

export const FilenameRestrictionModeSchema = z.enum(['unrestricted', 'windows', 'restricted'])
export type FilenameRestrictionMode = z.infer<typeof FilenameRestrictionModeSchema>

const DownloadSettingsSchema = z.object({
    verifyDownloadsCron: z.string(),
    maxConcurrentDownloads: z.number(),
    maxDownloadAttempts: z.number(),
    downloadTimeoutSeconds: z.number(),
    downloadRoot: z.string(),
    filenameRestrictionMode: FilenameRestrictionModeSchema,
    remuxVideoToMp4: z.boolean(),
    ffmpegPath: z.string(),
})

const FileWatcherSettingsSchema = z.object({
    enabled: z.boolean(),
    scanCron: z.string(),
    verifyFileSize: z.boolean(),
})

export const SettingsValuesSchema = z.object({
    logLevel: z.enum(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
    timezone: z.string(),
    crypto: CryptoFileSettingsSchema,
    loginSession: SessionSettingsSchema,
    dwApi: DailyWireAPISettingsSchema,
    movieMetadata: MovieMetadataSettingsSchema,
    dwOauth: OAuthSettingsSchema,
    dwTimeout: TimeoutSettingsSchema,
    scheduler: SchedulerSettingsSchema,
    newEpisodeSchedule: TrackNewEpisodeScheduleSchema,
    episodeStatusTiming: EpisodeStatusTimingSchema,
    downloadSettings: DownloadSettingsSchema,
    fileWatcher: FileWatcherSettingsSchema,
})
export type SettingsValues = z.infer<typeof SettingsValuesSchema>

const requiredNumber = () => z.number({error: 'A value is required.'})
const cronExpression = z.string().refine((value) => {
    const fields = value.trim().split(/\s+/)
    return fields.length === 5 && fields.every((field) => field.length > 0 && !field.includes('_'))
}, 'Enter a complete five-part cron expression.')
const metadataRefreshIntervals = z.string().refine((value) => {
    const unitSeconds: Record<string, number> = {
        s: 1,
        m: 60,
        h: 60 * 60,
        d: 60 * 60 * 24,
    }
    const tokens = value.split(',').map((token) => token.trim().toLowerCase())
    if (tokens.length === 0 || tokens.some((token) => token.length === 0)) return false

    let previous = 0
    for (const token of tokens) {
        const match = /^([1-9]\d*)([smhd])$/.exec(token)
        if (!match) return false
        const seconds = Number(match[1]) * unitSeconds[match[2]]
        if (!Number.isFinite(seconds) || seconds <= previous) return false
        previous = seconds
    }
    return true
}, 'Use unique, increasing comma-separated offsets such as 5m,15m,30m,1h,3h,6h,24h.')

export const SettingsFormSchema = SettingsValuesSchema.extend({
    loginSession: SessionSettingsSchema.extend({
        ttlSeconds: requiredNumber().int().min(60, 'Must be at least 60.'),
    }),
    movieMetadata: MovieMetadataSettingsSchema.extend({
        requestTimeoutSeconds: requiredNumber().min(1, 'Must be at least 1.'),
        maxRetries: requiredNumber().int().min(0, 'Must be 0 or greater.').max(5, 'Must be 5 or less.'),
    }),
    dwTimeout: TimeoutSettingsSchema.extend({
        minFastRequestMs: requiredNumber().int().min(0, 'Must be 0 or greater.'),
        maxFastRequests: requiredNumber().int().min(1, 'Must be at least 1.'),
        minSlowRequestMs: requiredNumber().int().min(0, 'Must be 0 or greater.'),
    }),
    scheduler: SchedulerSettingsSchema.extend({
        maxWorkers: requiredNumber().int().min(1, 'Must be at least 1.'),
        defaultMaxRetries: requiredNumber().int().min(0, 'Must be 0 or greater.'),
        retryBackoffSeconds: requiredNumber().min(0, 'Must be 0 or greater.'),
    }),
    newEpisodeSchedule: TrackNewEpisodeScheduleSchema.extend({
        findEpisodesCron: cronExpression,
        monitorEpisodeCron: cronExpression,
        checkNoShowTodayCron: cronExpression,
        metadataRefreshIntervals,
    }),
    episodeStatusTiming: EpisodeStatusTimingSchema.extend({
        publishedCountdownAfterMinutes: requiredNumber().int().min(0, 'Must be 0 or greater.'),
        publishedFinalAfterMinutes: requiredNumber().int().min(0, 'Must be 0 or greater.'),
    }),
    downloadSettings: DownloadSettingsSchema.extend({
        verifyDownloadsCron: cronExpression,
        maxConcurrentDownloads: requiredNumber().int().min(1, 'Must be at least 1.'),
        maxDownloadAttempts: requiredNumber().int().min(1, 'Must be at least 1.'),
        downloadTimeoutSeconds: requiredNumber().int().min(1, 'Must be at least 1.'),
    }),
    fileWatcher: FileWatcherSettingsSchema.extend({
        scanCron: cronExpression,
    }),
})

const WORKER_CRON_MINIMUM_MESSAGE = 'This worker runs more often than the configured DailyWire slow-request delay. Increase this cron interval, or change DailyWire → Request pacing → Minimum slow-request delay.'

export const SettingsServerErrors = createServerErrorMapper({
    'values.newEpisodeSchedule.findEpisodesCron': {worker_cron_interval_too_short: WORKER_CRON_MINIMUM_MESSAGE},
    'values.newEpisodeSchedule.monitorEpisodeCron': {worker_cron_interval_too_short: WORKER_CRON_MINIMUM_MESSAGE},
    'values.newEpisodeSchedule.checkNoShowTodayCron': {worker_cron_interval_too_short: WORKER_CRON_MINIMUM_MESSAGE},
    'values.downloadSettings.verifyDownloadsCron': {worker_cron_interval_too_short: WORKER_CRON_MINIMUM_MESSAGE},
    'values.fileWatcher.scanCron': {worker_cron_interval_too_short: WORKER_CRON_MINIMUM_MESSAGE},
})

export const SETTINGS_FIELD_PATHS = [
    'logLevel',
    'timezone',
    'crypto.secretKeyFile',
    'crypto.defaultSecretFile',
    'loginSession.ttlSeconds',
    'dwApi.middlewareApi',
    'dwApi.streamApi',
    'movieMetadata.tmdbReadAccessToken',
    'movieMetadata.tmdbApiBaseUrl',
    'movieMetadata.language',
    'movieMetadata.requestTimeoutSeconds',
    'movieMetadata.maxRetries',
    'dwOauth.issuer',
    'dwOauth.audience',
    'dwOauth.clientId',
    'dwOauth.scope',
    'dwTimeout.minFastRequestMs',
    'dwTimeout.maxFastRequests',
    'dwTimeout.minSlowRequestMs',
    'scheduler.enabled',
    'scheduler.maxWorkers',
    'scheduler.defaultMaxRetries',
    'scheduler.retryBackoffSeconds',
    'newEpisodeSchedule.findEpisodesCron',
    'newEpisodeSchedule.monitorEpisodeCron',
    'newEpisodeSchedule.checkNoShowTodayCron',
    'newEpisodeSchedule.metadataRefreshIntervals',
    'episodeStatusTiming.publishedCountdownAfterMinutes',
    'episodeStatusTiming.publishedFinalAfterMinutes',
    'downloadSettings.verifyDownloadsCron',
    'downloadSettings.maxConcurrentDownloads',
    'downloadSettings.maxDownloadAttempts',
    'downloadSettings.downloadTimeoutSeconds',
    'downloadSettings.downloadRoot',
    'downloadSettings.filenameRestrictionMode',
    'downloadSettings.remuxVideoToMp4',
    'downloadSettings.ffmpegPath',
    'fileWatcher.enabled',
    'fileWatcher.scanCron',
    'fileWatcher.verifyFileSize',
] as const

export const SettingsFieldPathSchema = z.enum(SETTINGS_FIELD_PATHS)
export type SettingsFieldPath = z.infer<typeof SettingsFieldPathSchema>

export const SettingsUpdateSchema = z.object({
    values: SettingsValuesSchema,
    changedFields: z.array(SettingsFieldPathSchema).min(1),
})
export type SettingsUpdate = z.infer<typeof SettingsUpdateSchema>

export const SettingsReadSchema = z.object({
    values: SettingsValuesSchema,
    configuredFields: z.array(SettingsFieldPathSchema),
    environmentOverrides: z.record(z.string(), z.string()),
    updatedAt: z.iso.datetime().nullable().transform((value) => value ? new Date(value) : null),
})
export type SettingsRead = z.infer<typeof SettingsReadSchema>
