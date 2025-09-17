import {z} from "zod";
import {createServerErrorMapper} from "../../utils/serverMessageMap";
import {PreferredFormat} from "../media_profile";

// Only override what you care about for this form.
export const MediaProfileServerErrors = createServerErrorMapper({
    name: {unique_violation: "Name is already taken."},
    slug: {unique_violation: "Slug is already taken."},
});


const MediaProfileBaseSchema = z.object({
    name: z.string().min(1, "Name is required"),
    outputTemplate: z.string().min(4).regex(/^\/downloads\//, "Output template must start with '/downloads/'").regex(/\.ext$/, "Output template must end with '.ext'"),
    preferredFormat: z.enum(PreferredFormat),
    downloadSeriesImages: z.boolean(),
})


export const MediaProfileCreateSchema = MediaProfileBaseSchema.extend({})
export type MediaProfileCreate = z.infer<typeof MediaProfileCreateSchema>;


export const MediaProfileReadSchema = MediaProfileBaseSchema.extend({
    id: z.number(),
    slug: z.string(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type MediaProfileRead = z.infer<typeof MediaProfileReadSchema>;


export const MediaProfileUpdateSchema = MediaProfileBaseSchema.extend({
    id: z.number(),
    slug: z.string(),
})
export type MediaProfileUpdate = z.infer<typeof MediaProfileUpdateSchema>;