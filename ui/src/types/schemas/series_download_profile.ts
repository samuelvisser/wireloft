import {z} from 'zod';
import {SeasonDetachedSchema, SeasonReadSchema} from "./season";
import {
    DownloadProfileSchemaRequest,
    DownloadProfileCreateSchema,
    DownloadProfileUpdateSchema,
    DownloadProfileSchemaResponse
} from "./download_profile_base";


// ---------- Strict request (create/update) ----------
const SeriesDownloadProfileBaseSchema = DownloadProfileSchemaRequest.extend({
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


export const SeriesDownloadProfileCreateSchema = SeriesDownloadProfileBaseSchema.safeExtend(
    DownloadProfileCreateSchema.shape
)
export type SeriesDownloadProfileCreateIn = z.input<typeof SeriesDownloadProfileCreateSchema>
export type SeriesDownloadProfileCreateOut = z.output<typeof SeriesDownloadProfileCreateSchema>


export const SeriesDownloadProfileUpdateSchema = SeriesDownloadProfileBaseSchema.safeExtend(
    DownloadProfileUpdateSchema.shape
)
export type SeriesDownloadProfileUpdateIn = z.input<typeof SeriesDownloadProfileUpdateSchema>
export type SeriesDownloadProfileUpdateOut = z.output<typeof SeriesDownloadProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const SeriesDownloadProfileReadSchema = DownloadProfileSchemaResponse.safeExtend({
    type: z.literal('series'),
    seasons: z.array(SeasonReadSchema),
    includeUpcomingSeasons: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type SeriesDownloadProfileRead = z.infer<typeof SeriesDownloadProfileReadSchema>