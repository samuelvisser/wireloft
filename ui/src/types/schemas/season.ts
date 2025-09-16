import {z} from "zod";

const SeasonBaseSchema = z.object({
    name: z.string(),
})


export const SeasonCreateSchema = SeasonBaseSchema.extend({
    dwId: z.string(),
    showId: z.string(),
    slug: z.string(),
})
export type SeasonCreate = z.infer<typeof SeasonCreateSchema>;


export const SeasonReadSchema = SeasonBaseSchema.extend({
    id: z.number(),
    dwId: z.string(),
    showId: z.string(),
    slug: z.string(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type SeasonRead = z.infer<typeof SeasonReadSchema>;


export const SeasonUpdateSchema = SeasonBaseSchema.extend({
})
export type SeasonUpdate = z.infer<typeof SeasonUpdateSchema>;