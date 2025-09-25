import {z} from 'zod';
import {SeasonDetachedSchema} from "./season";


// ---------- Strict request (create/update) ----------
const DownloadProfileSeriesBaseSchema = z.object({
    mediaProfileId: z.int(),
    enableProfile: z.boolean().default(true),
    seasons: z.array(SeasonDetachedSchema).default([]),
    includeUpcomingSeasons: z.boolean().default(true),
}).superRefine((v, ctx) => {
    if (!v.includeUpcomingSeasons && (!v.seasons || v.seasons.length === 0)) {
        ctx.addIssue({
            code: 'custom',
            path: ['seasons'],
            message: 'Choose at least one season or enable "Include upcoming seasons".',
        })
    }
})


export const DownloadProfileSeriesCreateSchema = DownloadProfileSeriesBaseSchema.safeExtend({
    showId: z.int(),
})
export type DownloadProfileSeriesCreateIn = z.input<typeof DownloadProfileSeriesCreateSchema>
export type DownloadProfileSeriesCreateOut = z.output<typeof DownloadProfileSeriesCreateSchema>


export const DownloadProfileSeriesUpdateSchema = DownloadProfileSeriesBaseSchema.safeExtend({})
export type DownloadProfileSeriesUpdateIn = z.input<typeof DownloadProfileSeriesUpdateSchema>
export type DownloadProfileSeriesUpdateOut = z.output<typeof DownloadProfileSeriesUpdateSchema>


// ------------ Lenient response (read) ------------
export const DownloadProfileSeriesReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    mediaProfileId: z.int().optional(),
    enableProfile: z.boolean(),
    seasons: z.array(SeasonDetachedSchema),
    includeUpcomingSeasons: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type DownloadProfileSeriesRead = z.infer<typeof DownloadProfileSeriesReadSchema>