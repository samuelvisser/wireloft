import {z} from 'zod';


// ---------- Strict request (create/update) ----------
const DownloadProfileSeriesBaseSchema = z.object({
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean(),
    includeUpcomingSeasons: z.boolean(),
})


export const DownloadProfileSeriesCreateSchema = DownloadProfileSeriesBaseSchema.extend({
    showId: z.number(),
})
export type DownloadProfileSeriesCreate = z.infer<typeof DownloadProfileSeriesCreateSchema>


export const DownloadProfileSeriesUpdateSchema = DownloadProfileSeriesBaseSchema.extend({
})
export type DownloadProfileSeriesUpdate = z.infer<typeof DownloadProfileSeriesUpdateSchema>


// ------------ Lenient response (read) ------------
export const DownloadProfileSeriesReadSchema = z.looseObject({
    id: z.number(),
    showId: z.number(),
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean(),
    includeUpcomingSeasons: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type DownloadProfileSeriesRead = z.infer<typeof DownloadProfileSeriesReadSchema>