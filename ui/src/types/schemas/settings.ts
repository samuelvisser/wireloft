import {z} from 'zod'


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
})

const EpisodeStatusTimingSchema = z.object({
    publishedCountdownAfterMinutes: z.number(),
    publishedFinalAfterMinutes: z.number(),
})

const DownloadSettingsSchema = z.object({
    verifyDownloadsCron: z.string(),
    maxConcurrentDownloads: z.number(),
    maxDownloadAttempts: z.number(),
    downloadTimeoutSeconds: z.number(),
    downloadRoot: z.string(),
    asciiOnlyFilenames: z.boolean(),
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
    dwOauth: OAuthSettingsSchema,
    dwTimeout: TimeoutSettingsSchema,
    scheduler: SchedulerSettingsSchema,
    newEpisodeSchedule: TrackNewEpisodeScheduleSchema,
    episodeStatusTiming: EpisodeStatusTimingSchema,
    downloadSettings: DownloadSettingsSchema,
    fileWatcher: FileWatcherSettingsSchema,
})
export type SettingsValues = z.infer<typeof SettingsValuesSchema>

export const SettingsUpdateSchema = z.object({
    values: SettingsValuesSchema,
})
export type SettingsUpdate = z.infer<typeof SettingsUpdateSchema>

export const SettingsReadSchema = z.object({
    values: SettingsValuesSchema,
    hasOverrides: z.boolean(),
    updatedAt: z.iso.datetime().nullable().transform((value) => value ? new Date(value) : null),
})
export type SettingsRead = z.infer<typeof SettingsReadSchema>
