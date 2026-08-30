import {z} from "zod";
import {MediaDownloadStatus} from "../media_download";


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
    startedAt: z.iso.datetime().transform((s) => new Date(s)).nullable(),
    finishedAt: z.iso.datetime().transform((s) => new Date(s)).nullable(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
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
    startedAt: z.iso.datetime().transform((s) => new Date(s)).nullable(),
    finishedAt: z.iso.datetime().transform((s) => new Date(s)).nullable(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MediaDownloadAttemptRead = z.infer<typeof MediaDownloadAttemptReadSchema>;
