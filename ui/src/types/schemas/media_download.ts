import {z} from "zod";
import {MediaDownloadStatus} from "../media_download";


const MediaDownloadBaseSchema = z.object({
    downloadStatus: z.enum(MediaDownloadStatus),
    filePath: z.string(),
})


export const MediaDownloadCreateSchema = MediaDownloadBaseSchema.extend({
})
export type MediaDownloadCreate = z.infer<typeof MediaDownloadCreateSchema>;


export const MediaDownloadReadSchema = MediaDownloadBaseSchema.extend({
    id: z.number(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type MediaDownloadRead = z.infer<typeof MediaDownloadReadSchema>;


export const MediaDownloadUpdateSchema = MediaDownloadBaseSchema.extend({
})
export type MediaDownloadUpdate = z.infer<typeof MediaDownloadUpdateSchema>;