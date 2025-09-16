import {z} from "zod";


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


export const MovieReadSchema = MovieBaseSchema.extend({
    id: z.number(),
    uuid: z.string(),
    dwId: z.string().optional(),
    slug: z.string(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type MovieRead = z.infer<typeof MovieReadSchema>;


export const MovieUpdateSchema = MovieBaseSchema.extend({
})
export type MovieUpdate = z.infer<typeof MovieUpdateSchema>;