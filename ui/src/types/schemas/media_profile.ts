import {z} from "zod";

const MediaProfileBaseSchema = z.object({
    name: z.string().min(1, "Name is required"),
    outputTemplate: z.string().min(3),
    preferredFormat: z.string(),
    downloadSeriesImages: z.boolean(),
})


export const MediaProfileCreateSchema = MediaProfileBaseSchema.extend({
})
export type MediaProfileCreate = z.infer<typeof MediaProfileCreateSchema>;


export const MediaProfileReadSchema = MediaProfileBaseSchema.extend({
    id: z.number(),
    slug: z.string(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type MediaProfileRead = z.infer<typeof MediaProfileReadSchema>;


export const MediaProfileUpdateSchema = MediaProfileBaseSchema.extend({
})
export type MediaProfileUpdate = z.infer<typeof MediaProfileUpdateSchema>;