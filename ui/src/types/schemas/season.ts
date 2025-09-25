import {z} from "zod";


// ---------- Strict request (create/update) ----------
const SeasonBaseSchema = z.object({
    name: z.string().min(1, "Name is required")
})

export const SeasonCreateSchema = SeasonBaseSchema.extend({
    dwId: z.string().min(1, "dwId missing"),
    showId: z.int().min(1, "showId missing"),
    slug: z.string().min(1, "slug missing"),
})
export type SeasonCreateIn = z.input<typeof SeasonCreateSchema>;
export type SeasonCreateOut = z.output<typeof SeasonCreateSchema>;


// Schema for seasons without external relations, allowing for dynamic insertion
export const SeasonDetachedSchema = SeasonCreateSchema.omit({
    showId: true,
})
export type SeasonDetachedIn = z.input<typeof SeasonDetachedSchema>;
export type SeasonDetachedOut = z.output<typeof SeasonDetachedSchema>;


export const SeasonUpdateSchema = SeasonBaseSchema.extend({
})
export type SeasonUpdateIn = z.input<typeof SeasonUpdateSchema>;
export type SeasonUpdateOut = z.output<typeof SeasonUpdateSchema>;


// ------------ Lenient response (read) ------------
export const SeasonReadSchema = z.looseObject({
    id: z.int(),
    name: z.string(),
    dwId: z.string(),
    showId: z.string(),
    slug: z.string(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type SeasonRead = z.infer<typeof SeasonReadSchema>;