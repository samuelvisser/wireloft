import {z} from 'zod';


// ---------- Strict request (create/update) ----------
const DownloadProfileSeriesBaseSchema = z.object({
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean().default(true),
    downloadSeasonList: z.array(z.string()),
    includeUpcomingSeasons: z.boolean().default(true),
})


export const DownloadProfileSeriesCreateSchema = DownloadProfileSeriesBaseSchema.extend({
    showId: z.number(),
})
export type DownloadProfileSeriesCreateIn = z.input<typeof DownloadProfileSeriesCreateSchema>
export type DownloadProfileSeriesCreateOut = z.output<typeof DownloadProfileSeriesCreateSchema>


export const DownloadProfileSeriesUpdateSchema = DownloadProfileSeriesBaseSchema.extend({
})
export type DownloadProfileSeriesUpdateIn = z.input<typeof DownloadProfileSeriesUpdateSchema>
export type DownloadProfileSeriesUpdateOut = z.output<typeof DownloadProfileSeriesUpdateSchema>


// ------------ Lenient response (read) ------------
export const DownloadProfileSeriesReadSchema = z.looseObject({
    id: z.number(),
    showId: z.number(),
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean(),
    downloadSeasonList: z.array(z.string()),
    includeUpcomingSeasons: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type DownloadProfileSeriesRead = z.infer<typeof DownloadProfileSeriesReadSchema>