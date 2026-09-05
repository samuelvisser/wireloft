import {z} from "zod";


export const MediaDownloadArtifactStatus = [
    'absent',
    'available',
    'missing',
    'corrupted',
] as const
export type MediaDownloadArtifactStatus = typeof MediaDownloadArtifactStatus[number]

// SQLite does not preserve timezone information for DateTime columns, even
// though WireLoft writes these values in UTC. Accept both representations and
// interpret unqualified persisted timestamps as UTC rather than browser-local.
const DatabaseDateTimeSchema = z.iso.datetime({local: true}).transform((value) =>
    new Date(/(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`),
)


// ---------- Strict request (create/update) ----------
const MediaDownloadBaseSchema = z.object({
    filePath: z.string(),
})

export const MediaDownloadCreateSchema = MediaDownloadBaseSchema.extend({})
export type MediaDownloadCreateIn = z.input<typeof MediaDownloadCreateSchema>;
export type MediaDownloadCreateOut = z.output<typeof MediaDownloadCreateSchema>;

export const MediaDownloadUpdateSchema = MediaDownloadBaseSchema.extend({})
export type MediaDownloadUpdateIn = z.input<typeof MediaDownloadUpdateSchema>;
export type MediaDownloadUpdateOut = z.output<typeof MediaDownloadUpdateSchema>;


// ------------ Persistent domain response ------------
export const MediaDownloadReadSchema = z.looseObject({
    id: z.int(),
    type: z.string(),
    mediaItemId: z.int(),
    localMediaProfileId: z.int(),
    filePath: z.string(),
    artifactStatus: z.enum(MediaDownloadArtifactStatus),
    artifactError: z.string().nullable(),
    automaticRetrySuppressed: z.boolean(),
    downloadedBytes: z.int().nullable(),
    formatDownloaded: z.string().nullable(),
    downloadedAt: DatabaseDateTimeSchema.nullable(),
    createdAt: DatabaseDateTimeSchema,
    updatedAt: DatabaseDateTimeSchema,
})
export type MediaDownloadRead = z.infer<typeof MediaDownloadReadSchema>;


export const MediaDownloadViewReadSchema = MediaDownloadReadSchema.extend({
    mediaSlug: z.string().nullable(),
    mediaTitle: z.string().nullable(),
    episodeSlug: z.string().nullable(),
    episodeTitle: z.string().nullable(),
    episodeIdentifier: z.string().nullable(),
    showSlug: z.string().nullable(),
    showTitle: z.string().nullable(),
    movieSlug: z.string().nullable(),
    movieTitle: z.string().nullable(),
    movieExtraType: z.string().nullable(),
    localMediaProfileName: z.string().nullable(),
    preferredFormat: z.string().nullable(),
    downloadedPublishStatus: z.string().nullable(),
    latestAttemptStatus: z.string().nullable(),
    latestAttemptError: z.string().nullable(),
    latestAttemptIsRedownload: z.boolean().nullable(),
    latestAttemptStartedAt: DatabaseDateTimeSchema.nullable(),
    latestAttemptFinishedAt: DatabaseDateTimeSchema.nullable(),
})
export type MediaDownloadDomainViewRead = z.infer<typeof MediaDownloadViewReadSchema>;

/**
 * Presentation view consumed by existing download UI.
 *
 * The fields below are deliberately not part of MediaDownload's API schema.
 * They are derived in queries.ts from generic media.download TaskOperations
 * (while execution is active) or immutable attempt history (afterwards).
 */
export type MediaDownloadViewRead = MediaDownloadDomainViewRead & {
    downloadStatus: string
    progress: number
    errorMessage: string | null
    startedAt: Date | null
    finishedAt: Date | null
    isRedownloadAttempt: boolean | null
}


// ------------ Historical attempt ledger ------------
export const MediaDownloadAttemptReadSchema = z.looseObject({
    id: z.int(),
    mediaDownloadId: z.int(),
    isRedownload: z.boolean(),
    status: z.string(),
    errorMessage: z.string().nullable(),
    downloadedBytes: z.int().nullable(),
    formatDownloaded: z.string().nullable(),
    startedAt: DatabaseDateTimeSchema.nullable(),
    finishedAt: DatabaseDateTimeSchema.nullable(),
    createdAt: DatabaseDateTimeSchema,
})
export type MediaDownloadAttemptRead = z.infer<typeof MediaDownloadAttemptReadSchema>;
