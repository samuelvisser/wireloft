import {z} from "zod";

import {ApiDateTimeSchema} from "./datetime";


export const MediaDownloadArtifactStatus = [
    'absent',
    'available',
    'missing',
    'corrupted',
] as const
export type MediaDownloadArtifactStatus = typeof MediaDownloadArtifactStatus[number]


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
    downloadedAt: ApiDateTimeSchema.nullable(),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
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
    latestTaskStatus: z.string().nullable(),
    latestTaskError: z.string().nullable(),
    latestTaskIsRedownload: z.boolean().nullable(),
    latestTaskStartedAt: ApiDateTimeSchema.nullable(),
    latestTaskFinishedAt: ApiDateTimeSchema.nullable(),
})
export type MediaDownloadDomainViewRead = z.infer<typeof MediaDownloadViewReadSchema>;

/**
 * Presentation view consumed by the download UI.
 *
 * Live execution data comes from generic media.download TaskOperations. Once an
 * operation is no longer active, the latest canonical TaskRun facts supplied by
 * the domain view provide the stable presentation fallback.
 */
export type MediaDownloadViewRead = MediaDownloadDomainViewRead & {
    downloadStatus: string
    progress: number
    errorMessage: string | null
    startedAt: Date | null
    finishedAt: Date | null
    isRedownloadAttempt: boolean | null
}
