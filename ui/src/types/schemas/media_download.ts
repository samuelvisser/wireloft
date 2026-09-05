import {z} from "zod";
import {MediaDownloadStatus} from "../media_download";


// SQLite does not preserve timezone information for DateTime columns, even
// though WireLoft writes these values in UTC. Pydantic therefore serializes
// persisted timestamps such as "2026-09-05T08:04:12.123456" without a trailing
// offset. Accept both that representation and ordinary UTC ISO timestamps, and
// interpret unqualified database values as UTC rather than browser-local time.
const DatabaseDateTimeSchema = z.iso.datetime({local: true}).transform((value) =>
    new Date(/Z$/i.test(value) ? value : `${value}Z`),
)


// ---------- Strict request (create/update) ----------
const MediaDownloadBaseSchema = z.object({
    downloadStatus: z.enum(MediaDownloadStatus),
    filePath: z.string(),
})


export const MediaDownloadCreateSchema = MediaDownloadBaseSchema.extend({
})
export type MediaDownloadCreateIn = z.input<typeof MediaDownloadCreateSchema>;
export type MediaDownloadCreateOut = z.output<typeof MediaDownloadCreateSchema>;


export const MediaDownloadUpdateSchema = MediaDownloadBaseSchema.extend({
})
export type MediaDownloadUpdateIn = z.input<typeof MediaDownloadUpdateSchema>;
export type MediaDownloadUpdateOut = z.output<typeof MediaDownloadUpdateSchema>;


// ------------ Lenient response (read) ------------
export const MediaDownloadReadSchema = z.looseObject({
    id: z.int(),
    type: z.string(),
    mediaItemId: z.int(),
    localMediaProfileId: z.int(),
    downloadStatus: z.string(),
    filePath: z.string(),
    progress: z.int(),
    errorMessage: z.string().nullable(),
    downloadedBytes: z.int().nullable(),
    formatDownloaded: z.string().nullable(),
    startedAt: DatabaseDateTimeSchema.nullable(),
    finishedAt: DatabaseDateTimeSchema.nullable(),
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
    isRedownloadAttempt: z.boolean().nullable(),
    downloadedPublishStatus: z.string().nullable(),
})
export type MediaDownloadViewRead = z.infer<typeof MediaDownloadViewReadSchema>;


// ------------ Lenient response (read): one entry in a download's attempt ledger ------------
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
