import {z} from 'zod';
import {EpisodePublishStatus} from "../episode";


// ---------- Strict request (create/update) ----------
const EpisodeBaseSchema = z.object({
    publishStatus: z.enum(EpisodePublishStatus),
    wentLiveDate: z.date().optional(),
    publishedDate: z.date().optional(),
    redownloadedDate: z.date().optional(),
    title: z.string(),
    description: z.string(),
    downloadedDate: z.date().optional(),
})


export const EpisodeCreateSchema = EpisodeBaseSchema.extend({
    showId: z.number(),
    index: z.number(),
    dwId: z.string().optional(),
    slug: z.string(),
})
export type EpisodeCreateIn = z.input<typeof EpisodeCreateSchema>
export type EpisodeCreateOut = z.output<typeof EpisodeCreateSchema>


export const EpisodeUpdateSchema = EpisodeBaseSchema.extend({
    dwId: z.string().optional(),
})
export type EpisodeUpdateIn = z.input<typeof EpisodeUpdateSchema>
export type EpisodeUpdateOut = z.output<typeof EpisodeUpdateSchema>


// ------------ Lenient response (read) ------------
export const EpisodeReadSchema = z.looseObject({
    id: z.number(),
    showId: z.number(),
    index: z.number(),
    publishStatus: z.union([z.enum(EpisodePublishStatus), z.string()]),
    wentLiveDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    publishedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    redownloadedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    title: z.string(),
    description: z.string(),
    downloadedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    uuid: z.string(),
    dwId: z.string().optional(),
    slug: z.string(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type EpisodeRead = z.infer<typeof EpisodeReadSchema>