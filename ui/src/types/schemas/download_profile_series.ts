import {z} from 'zod';


const DownloadProfileSeriesBaseSchema = z.object({
    media_profile_id: z.number().optional(),
    enable_profile: z.boolean(),
    include_upcoming_seasons: z.boolean(),
})


export const DownloadProfileSeriesCreateSchema = DownloadProfileSeriesBaseSchema.extend({
    show_id: z.number(),
})
export type DownloadProfileSeriesCreate = z.infer<typeof DownloadProfileSeriesCreateSchema>


export const DownloadProfileSeriesReadSchema = DownloadProfileSeriesBaseSchema.extend({
    id: z.number(),
    show_id: z.number(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type DownloadProfileSeriesRead = z.infer<typeof DownloadProfileSeriesReadSchema>


export const DownloadProfileSeriesUpdateSchema = DownloadProfileSeriesBaseSchema.extend({
})
export type DownloadProfileSeriesUpdate = z.infer<typeof DownloadProfileSeriesUpdateSchema>