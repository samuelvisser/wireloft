import {z} from "zod";


// ---------- Strict request (create/update) ----------
const MovieBaseSchema = z.object({
    title: z.string(),
    description: z.string().optional(),
    downloadedDate: z.date().optional(),
})


export const MovieCreateSchema = MovieBaseSchema.extend({
    dwId: z.string().optional(),
    slug: z.string(),
})
export type MovieCreate = z.infer<typeof MovieCreateSchema>;


export const MovieUpdateSchema = MovieBaseSchema.extend({
})
export type MovieUpdate = z.infer<typeof MovieUpdateSchema>;


// ------------ Lenient response (read) ------------
export const MovieReadSchema = z.looseObject({
    id: z.number(),
    uuid: z.string(),
    dwId: z.string().optional(),
    slug: z.string(),
    title: z.string(),
    description: z.string().optional(),
    downloadedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MovieRead = z.infer<typeof MovieReadSchema>;