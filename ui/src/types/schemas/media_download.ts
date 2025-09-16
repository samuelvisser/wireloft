import {z} from "zod";
import {MediaDownloadStatus} from "../media_download";


const MediaDownloadBaseSchema = z.object({
    download_status: z.enum(MediaDownloadStatus),
    file_path: z.string(),
})


export const MediaDownloadCreateSchema = MediaDownloadBaseSchema.extend({
})
export type MediaDownloadCreate = z.infer<typeof MediaDownloadCreateSchema>;


export const MediaDownloadReadSchema = MediaDownloadBaseSchema.extend({
    id: z.number(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type MediaDownloadRead = z.infer<typeof MediaDownloadReadSchema>;


export const MediaDownloadUpdateSchema = MediaDownloadBaseSchema.extend({
})
export type MediaDownloadUpdate = z.infer<typeof MediaDownloadUpdateSchema>;