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
    id: z.number(),
    downloadStatus: z.union([z.enum(MediaDownloadStatus), z.string()]),
    filePath: z.string(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MediaDownloadRead = z.infer<typeof MediaDownloadReadSchema>;