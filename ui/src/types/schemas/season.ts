import {z} from "zod";

import {ApiDateTimeSchema} from "./datetime";


// ---------- Strict request (create/update) ----------
const SeasonBaseSchema = z.object({
    name: z.string().min(1, "Name is required")
})

export const SeasonCreateSchema = SeasonBaseSchema.extend({
    showId: z.int().min(1, "showId missing"),
    index: z.int(),
    slug: z.string().min(1, "slug missing"),
})
export type SeasonCreateIn = z.input<typeof SeasonCreateSchema>;
export type SeasonCreateOut = z.output<typeof SeasonCreateSchema>;


export const SeasonDetachedSchema = SeasonCreateSchema.omit({
    showId: true,
    index: true,
})
export type SeasonDetachedIn = z.input<typeof SeasonDetachedSchema>;
export type SeasonDetachedOut = z.output<typeof SeasonDetachedSchema>;


export const SeasonUpdateSchema = SeasonBaseSchema.extend({
    index: z.int(),
})
export type SeasonUpdateIn = z.input<typeof SeasonUpdateSchema>;
export type SeasonUpdateOut = z.output<typeof SeasonUpdateSchema>;


// ------------ Lenient response (read) ------------
export const SeasonReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    index: z.int(),
    name: z.string(),
    slug: z.string(),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type SeasonRead = z.infer<typeof SeasonReadSchema>;
