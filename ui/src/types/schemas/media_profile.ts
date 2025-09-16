import {z} from "zod";

const MediaProfileBaseSchema = z.object({
    name: z.string().min(1, "Name is required"),
    output_template: z.string().min(3),
    preferred_format: z.string(),
    download_series_images: z.boolean(),
})


export const MediaProfileCreateSchema = MediaProfileBaseSchema.extend({
})
export type MediaProfileCreate = z.infer<typeof MediaProfileCreateSchema>;


export const MediaProfileReadSchema = MediaProfileBaseSchema.extend({
    id: z.number(),
    slug: z.string(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type MediaProfileRead = z.infer<typeof MediaProfileReadSchema>;


export const MediaProfileUpdateSchema = MediaProfileBaseSchema.extend({
})
export type MediaProfileUpdate = z.infer<typeof MediaProfileUpdateSchema>;