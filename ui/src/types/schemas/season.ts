import {z} from "zod";


// ---------- Strict request (create/update) ----------
const SeasonBaseSchema = z.object({
    name: z.string(),
})


export const SeasonCreateSchema = SeasonBaseSchema.extend({
    dwId: z.string(),
    showId: z.string(),
    slug: z.string(),
})
export type SeasonCreate = z.infer<typeof SeasonCreateSchema>;


export const SeasonUpdateSchema = SeasonBaseSchema.extend({
})
export type SeasonUpdate = z.infer<typeof SeasonUpdateSchema>;


// ------------ Lenient response (read) ------------
export const SeasonReadSchema = z.looseObject({
    id: z.number(),
    name: z.string(),
    dwId: z.string(),
    showId: z.string(),
    slug: z.string(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type SeasonRead = z.infer<typeof SeasonReadSchema>;