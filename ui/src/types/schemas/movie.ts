import {z} from "zod";


const MovieBaseSchema = z.object({
    title: z.string(),
    description: z.string().optional(),
    downloaded_date: z.date().optional(),
})


export const MovieCreateSchema = MovieBaseSchema.extend({
    dw_id: z.string().optional(),
    slug: z.string(),
})
export type MovieCreate = z.infer<typeof MovieCreateSchema>;


export const MovieReadSchema = MovieBaseSchema.extend({
    id: z.number(),
    uuid: z.string(),
    dw_id: z.string().optional(),
    slug: z.string(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type MovieRead = z.infer<typeof MovieReadSchema>;


export const MovieUpdateSchema = MovieBaseSchema.extend({
})
export type MovieUpdate = z.infer<typeof MovieUpdateSchema>;