import {z} from "zod";

const SeasonBaseSchema = z.object({
    name: z.string(),
})


export const SeasonCreateSchema = SeasonBaseSchema.extend({
    dw_id: z.string(),
    show_id: z.string(),
    slug: z.string(),
})
export type SeasonCreate = z.infer<typeof SeasonCreateSchema>;


export const SeasonReadSchema = SeasonBaseSchema.extend({
    id: z.number(),
    dw_id: z.string(),
    show_id: z.string(),
    slug: z.string(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type SeasonRead = z.infer<typeof SeasonReadSchema>;


export const SeasonUpdateSchema = SeasonBaseSchema.extend({
})
export type SeasonUpdate = z.infer<typeof SeasonUpdateSchema>;