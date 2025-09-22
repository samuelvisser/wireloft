import {z} from "zod";
import {createServerErrorMapper} from "../../utils/serverMessageMap";
import {PreferredFormatReg} from "../media_profile";

// Only override what you care about for this form.
export const MediaProfileServerErrors = createServerErrorMapper({
    name: {unique_violation: "Name is already taken."},
    slug: {unique_violation: "Slug is already taken."},
});

// ---------- Strict request (create/update) ----------
const MediaProfileBaseSchema = z.object({
    name: z.string().min(1, "Name is required"),
    outputTemplate: z.string()
        .regex(/^\/downloads\//, "Output template must start with '/downloads/'")
        .regex(/\.ext$/, "Output template must end with '.ext'")
        .min(16),
    preferredFormat: z.enum(PreferredFormatReg.values),
    downloadSeriesImages: z.boolean(),
})


export const MediaProfileCreateSchema = MediaProfileBaseSchema.extend({
    outputTemplate: MediaProfileBaseSchema.shape.outputTemplate.default('/downloads/'),
    preferredFormat: MediaProfileBaseSchema.shape.preferredFormat.default('format_1080p'),
    downloadSeriesImages: MediaProfileBaseSchema.shape.downloadSeriesImages.default(true),
})
export type MediaProfileCreateIn = z.input<typeof MediaProfileCreateSchema>;
export type MediaProfileCreateOut = z.output<typeof MediaProfileCreateSchema>;


export const MediaProfileUpdateSchema = MediaProfileBaseSchema.extend({
    id: z.number(),
    slug: z.string(),
})
export type MediaProfileUpdateIn = z.input<typeof MediaProfileUpdateSchema>;
export type MediaProfileUpdateOut = z.output<typeof MediaProfileUpdateSchema>;


// ------------ Lenient response (read) ------------
export const MediaProfileReadSchema = z.looseObject({
    id: z.number(),
    slug: z.string(),
    name: z.string(),
    outputTemplate: z.string(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    downloadSeriesImages: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MediaProfileRead = z.infer<typeof MediaProfileReadSchema>;
