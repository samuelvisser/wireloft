import {z} from 'zod';


const DownloadProfileSeriesBaseSchema = z.object({
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean(),
    includeUpcomingSeasons: z.boolean(),
})


export const DownloadProfileSeriesCreateSchema = DownloadProfileSeriesBaseSchema.extend({
    showId: z.number(),
})
export type DownloadProfileSeriesCreate = z.infer<typeof DownloadProfileSeriesCreateSchema>


export const DownloadProfileSeriesReadSchema = DownloadProfileSeriesBaseSchema.extend({
    id: z.number(),
    showId: z.number(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type DownloadProfileSeriesRead = z.infer<typeof DownloadProfileSeriesReadSchema>


export const DownloadProfileSeriesUpdateSchema = DownloadProfileSeriesBaseSchema.extend({
})
export type DownloadProfileSeriesUpdate = z.infer<typeof DownloadProfileSeriesUpdateSchema>